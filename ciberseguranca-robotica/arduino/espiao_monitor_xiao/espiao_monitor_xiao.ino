// espiao_monitor_xiao.ino - ESPIAO em MODO MONITOR (promiscuo) num XIAO ESP32-C6.
//
// Versao que INTERPRETA o comando: o botao BOOT repete o ultimo MOVIMENTO capturado
// (F/T/E/D de 1 byte; ignora o P). Funciona bem com trafego em TEXTO CLARO.
//
// *** DIDATICO: esta versao NAO funciona contra a cifra. ***
// Contra controle_cripto.py os frames sao 16 bytes embaralhados; o espiao captura,
// mas nao reconhece nenhum movimento -> BOOT responde "nenhum movimento capturado".
// Mostre isto falhando em aula; depois grave espiao_monitor_xiao_cif.ino, que repete
// os bytes VERBATIM (sem entender) e faz o robo obedecer mesmo cifrado.
//
// Variante sem M5Unified (o XIAO nao e M5): saida pela Serial e por um LED simples.
// A cada frame ESP-NOW capturado no canal o LED pisca e a Serial imprime o comando.
//
// Mais facil de gravar que a Capsule: BOOT/RESET acessiveis, auto-reset costuma
// funcionar. Se precisar: segure BOOT, aperte RESET, solte BOOT, e grave.
//
// Requisitos: core esp32 (Espressif). Nenhuma biblioteca extra. FQBN XIAO_ESP32C6.
//   arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao
//   arduino-cli upload  -p <porta> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao

#include <WiFi.h>
#include "esp_wifi.h"
#include "esp_now.h"

// ====================== CONFIGURACAO ======================
static const uint8_t CANAL = 1;               // mesmo canal de todas as placas

// MAC do ROBO: destino do replay. Descubra com ferramentas/mostra_mac.py no robo.
static uint8_t ROBO_MAC[6] = { 0x48, 0x27, 0xe2, 0xe3, 0xac, 0x78 };

// XIAO ESP32-C6: LED de usuario no GPIO15 (ativo em nivel BAIXO), BOOT no GPIO9.
#ifndef LED_BUILTIN
#define LED_BUILTIN 15
#endif
#define PINO_LED        LED_BUILTIN
#define LED_ATIVO_BAIXO 1
#define PINO_BOTAO      9
#define BODY_MAX        32
// ==========================================================

static const uint8_t BROADCAST[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };

struct Cap {
  uint8_t src[6];
  uint8_t body[BODY_MAX];
  uint8_t len;
};

#define QN 16
static volatile uint8_t q_head = 0, q_tail = 0;
static Cap q[QN];

static Cap  ultimo;
static bool tem_ultimo = false;
static Cap  ultimo_mov;                       // ultimo comando de MOVIMENTO (F/T/E/D)
static bool tem_mov = false;                  // alvo do replay (ignora o P)
static long total = 0;

static const char* nomeComando(const Cap& c) {
  if (c.len == 1) {
    switch (c.body[0]) {
      case 'F': return "FRENTE";
      case 'T': return "TRAS";
      case 'E': return "ESQ";
      case 'D': return "DIR";
      case 'P': return "PARAR";
    }
  }
  return "?";                                 // nao sabe ler (ex.: cifrado)
}

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

static void sniffer(void* buf, wifi_promiscuous_pkt_type_t type) {
  const wifi_promiscuous_pkt_t* pkt = (const wifi_promiscuous_pkt_t*)buf;
  const uint8_t* p = pkt->payload;
  int len = pkt->rx_ctrl.sig_len;
  if (len < 40) return;

  if (p[24] != 0x7F) return;                  // vendor-specific action
  if (p[32] != 0xDD) return;                  // element vendor-specific
  if (p[34] != 0x18 || p[35] != 0xFE || p[36] != 0x34) return;  // OUI Espressif
  if (p[37] != 0x04) return;                  // tipo ESP-NOW

  const uint8_t* da = p + 4;
  bool para_robo = (memcmp(da, ROBO_MAC, 6) == 0);
  bool bcast     = (memcmp(da, BROADCAST, 6) == 0);
  if (!para_robo && !bcast) return;

  int bodylen = p[33] - 5;
  if (bodylen < 1) return;
  if (39 + bodylen > len) bodylen = len - 39;
  if (bodylen > BODY_MAX) bodylen = BODY_MAX;

  uint8_t next = (q_head + 1) % QN;
  if (next == q_tail) return;
  memcpy(q[q_head].src, p + 10, 6);
  memcpy(q[q_head].body, p + 39, bodylen);
  q[q_head].len = bodylen;
  q_head = next;
}

static void macStr(const uint8_t* m, char* out) {
  sprintf(out, "%02x:%02x:%02x:%02x:%02x:%02x", m[0], m[1], m[2], m[3], m[4], m[5]);
}

static void enviarReplay() {
  // So repete o que reconheceu como MOVIMENTO. Contra a cifra, nunca reconhece.
  if (!tem_mov) { Serial.println("replay: nenhum movimento capturado ainda"); return; }
  esp_err_t r = esp_now_send(ROBO_MAC, ultimo_mov.body, ultimo_mov.len);
  Serial.printf("REPLAY -> %s (%s)\n", nomeComando(ultimo_mov), r == ESP_OK ? "ok" : "falhou");
  ledPisca(3, 60);
}

void setup() {
  pinMode(PINO_LED, OUTPUT); ledSet(false);
  pinMode(PINO_BOTAO, INPUT_PULLUP);
  Serial.begin(115200);
  delay(200);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(CANAL, WIFI_SECOND_CHAN_NONE);

  if (esp_now_init() == ESP_OK) {
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
  Serial.println("ESPIAO monitor (XIAO ESP32-C6) - le o comando");
  Serial.printf("Canal %d  destino replay %s\n", CANAL, mac);
  Serial.println("Botao BOOT = replay do ultimo MOVIMENTO (ignora P)");
  Serial.println("========================================");
  ledPisca(2, 150);
}

static bool botao_ant = false;

void loop() {
  while (q_tail != q_head) {
    ultimo = q[q_tail];
    tem_ultimo = true;
    q_tail = (q_tail + 1) % QN;
    total++;
    char mac[18]; macStr(ultimo.src, mac);
    Serial.printf("[%ld] capturou %s de %s\n", total, nomeComando(ultimo), mac);
    // Guarda so os movimentos como alvo do replay (P nao vira replay; cifra nunca casa).
    char mv = (ultimo.len == 1) ? ultimo.body[0] : 0;
    if (mv == 'F' || mv == 'T' || mv == 'E' || mv == 'D') { ultimo_mov = ultimo; tem_mov = true; }
    ledPisca(1, 40);
  }

  bool pressionado = (digitalRead(PINO_BOTAO) == LOW);
  if (pressionado && !botao_ant) { delay(20); if (digitalRead(PINO_BOTAO) == LOW) enviarReplay(); }
  botao_ant = pressionado;

  delay(10);
}
