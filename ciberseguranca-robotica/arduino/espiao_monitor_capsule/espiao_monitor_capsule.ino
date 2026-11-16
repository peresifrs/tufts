// espiao_monitor_capsule.ino - ESPIAO em MODO MONITOR (promiscuo) numa M5 Capsule.
//
// Variante SEM TELA do espiao_monitor: a Capsule nao tem display, entao a saida
// e pelo LED RGB da placa (cor = ultimo comando capturado) e pela Serial (bom no
// projetor). O botao da Capsule faz REPLAY do ultimo comando capturado.
//
// Por que Arduino/C: o MicroPython (UiFlow2) NAO expoe modo monitor. Quando o
// controle manda UNICAST (controle_unicast.py), um espiao ESP-NOW comum nao ve
// mais nada. Em promiscuo, a Capsule le TODO frame do canal e captura o unicast.
// Licao: endereçar != cifrar.
//
// Mantido separado do espiao MicroPython com tela (que continua intacto noutra
// placa). Assim nao se regrava firmware de ida e volta: cada no numa placa.
//
// Requisitos (Arduino IDE / arduino-cli):
//   - Core esp32 (Espressif). Biblioteca M5Unified (so para abstrair o botao).
//   - FQBN: esp32:esp32:m5stack_capsule
// Gravar daqui:
//   arduino-cli compile --fqbn esp32:esp32:m5stack_capsule arduino/espiao_monitor_capsule
//   arduino-cli upload -p <porta-capsule> --fqbn esp32:esp32:m5stack_capsule arduino/espiao_monitor_capsule

#include <M5Unified.h>
#include <WiFi.h>
#include "esp_wifi.h"
#include "esp_now.h"

// ====================== CONFIGURACAO ======================
static const uint8_t CANAL = 1;               // mesmo canal de todas as placas

// MAC do ROBO: destino do unicast do controle e do replay deste espiao.
// Descubra com: mpremote connect <porta-robo> run micropython/ferramentas/mostra_mac.py
static uint8_t ROBO_MAC[6] = { 0x48, 0x27, 0xe2, 0xe3, 0xac, 0x78 };

// LED RGB onboard da Capsule. CONFIRME o pino (a M5Capsule usa GPIO21; se a cor
// nao acender, teste outro pino ou veja o pinout do seu modelo).
#define PINO_LED 21
#define BODY_MAX 32                           // bytes de payload guardados por item
// ==========================================================

static const uint8_t BROADCAST[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };

// ---------- Fila do callback (promiscuo) para o loop() ----------
struct Cap {
  uint8_t src[6];
  uint8_t body[BODY_MAX];
  uint8_t len;
};
#define QN 16
static volatile uint8_t q_head = 0, q_tail = 0;
static Cap q[QN];

// ---------- Ultimo comando capturado (para replay e LED) ----------
static Cap  ultimo;
static bool tem_ultimo = false;
static long total = 0;

// ---------- Nome e cor do comando ----------
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
  return "?";
}

static void ledCor(uint8_t r, uint8_t g, uint8_t b) {
  // neopixelWrite(pino, R, G, B) - helper do core esp32 (sem biblioteca extra).
  neopixelWrite(PINO_LED, r, g, b);
}

static void ledComando(const Cap& c) {
  if (c.len == 1) {
    switch (c.body[0]) {
      case 'F': ledCor(0, 40, 0);  return;   // verde
      case 'T': ledCor(40, 0, 0);  return;   // vermelho
      case 'E': ledCor(0, 0, 40);  return;   // azul
      case 'D': ledCor(40, 20, 0); return;   // laranja
      case 'P': ledCor(2, 2, 8);   return;   // azul fraco
    }
  }
  ledCor(10, 10, 10);                         // payload generico: branco fraco
}

// ---------- Callback do modo promiscuo ----------
// Layout ESP-NOW no ar: cabecalho 802.11 (24) + category 0x7F + OUI + random +
// element 0xDD/length/OUI/type 0x04/versao + payload (offset 39).
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
  if (!para_robo && !bcast) return;           // foca o trafego para o robo

  int bodylen = p[33] - 5;
  if (bodylen < 1) return;
  if (39 + bodylen > len) bodylen = len - 39;
  if (bodylen > BODY_MAX) bodylen = BODY_MAX;

  uint8_t next = (q_head + 1) % QN;
  if (next == q_tail) return;                 // fila cheia: descarta
  memcpy(q[q_head].src, p + 10, 6);           // origem (addr2)
  memcpy(q[q_head].body, p + 39, bodylen);
  q[q_head].len = bodylen;
  q_head = next;
}

static void macStr(const uint8_t* m, char* out) {
  sprintf(out, "%02x:%02x:%02x:%02x:%02x:%02x", m[0], m[1], m[2], m[3], m[4], m[5]);
}

// ---------- Replay ----------
static void enviarReplay() {
  if (!tem_ultimo) { Serial.println("replay: nada capturado ainda"); return; }
  esp_err_t r = esp_now_send(ROBO_MAC, ultimo.body, ultimo.len);
  Serial.printf("REPLAY -> %s (%s)\n", nomeComando(ultimo), r == ESP_OK ? "ok" : "falhou");
  // Piscada branca para confirmar o replay, depois volta a cor do comando.
  ledCor(60, 60, 60); delay(120);
  ledComando(ultimo);
}

// ---------- Setup ----------
void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);
  delay(200);
  ledCor(0, 0, 0);

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
  Serial.println("ESPIAO monitor (Capsule, sem tela)");
  Serial.printf("Canal %d  destino replay %s\n", CANAL, mac);
  Serial.println("Botao = replay do ultimo capturado");
  Serial.println("========================================");
  ledCor(0, 2, 2);                            // ciano fraco = pronto/ouvindo
}

// ---------- Loop ----------
void loop() {
  M5.update();

  while (q_tail != q_head) {
    ultimo = q[q_tail];
    tem_ultimo = true;
    q_tail = (q_tail + 1) % QN;
    total++;
    char mac[18]; macStr(ultimo.src, mac);
    Serial.printf("[%ld] capturou %s de %s\n", total, nomeComando(ultimo), mac);
    ledComando(ultimo);
  }

  if (M5.BtnA.wasPressed()) enviarReplay();

  delay(15);
}
