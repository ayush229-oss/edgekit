//+------------------------------------------------------------------+
//| EdgekitConnector.mq5                                             |
//| Connects MetaTrader 5 to Edgekit live-demo forward tests.        |
//|                                                                  |
//| Setup                                                            |
//| -----                                                            |
//| 1. Copy this file to:  File → Open Data Folder → MQL5/Experts   |
//| 2. Press F5 in Navigator to refresh — EA appears under Experts   |
//| 3. Tools → Options → Expert Advisors → Allow WebRequest          |
//|    → add:  http://165.232.178.128:8765                           |
//| 4. Drag EA onto any chart, set InpToken in Properties            |
//|    (get your token at https://edgekit.uk/resources)              |
//+------------------------------------------------------------------+
#property copyright "Edgekit.uk"
#property link      "https://edgekit.uk"
#property version   "1.01"
#property description "Live-demo forward test connector for Edgekit."
#property strict

//-- Inputs -----------------------------------------------------------
input string InpToken    = "";                             // Bridge token (from edgekit.uk/resources)
input string InpVpsUrl   = "http://165.232.178.128:8765"; // VPS URL
input int    InpPollSecs = 30;                            // Poll interval (seconds)

//-- Constants --------------------------------------------------------
#define MAX_TESTS 50
#define MAGIC     770011

//-- Per-test state ---------------------------------------------------
struct FTState {
   long   ft_id;
   string last_bar;   // bar_time we last acted on (dedup)
   long   ticket;     // open MT5 ticket, or -1 if flat
};
FTState g_state[MAX_TESTS];
int     g_n = 0;

//+------------------------------------------------------------------+
int StateIdx(long ft_id) {
   for(int i = 0; i < g_n; i++)
      if(g_state[i].ft_id == ft_id) return i;
   if(g_n < MAX_TESTS) {
      g_state[g_n].ft_id    = ft_id;
      g_state[g_n].last_bar = "";
      g_state[g_n].ticket   = -1;
      g_n++;
      return g_n - 1;
   }
   return -1;
}

//-- Helpers: char[] ↔ string -----------------------------------------
string CharsToStr(char &arr[]) {
   string s = "";
   for(int i = 0; i < ArraySize(arr); i++) {
      if(arr[i] == 0) break;
      s += CharToStr(arr[i]);
   }
   return s;
}

void StrToChars(string src, char &dst[]) {
   int n = StringLen(src);
   ArrayResize(dst, n);
   for(int i = 0; i < n; i++)
      dst[i] = (char)StringGetCharacter(src, i);
}

//-- Minimal JSON helpers: extract Nth object from array, get field --
int CountObjects(string json) {
   int count = 0, depth = 0;
   for(int i = 0; i < StringLen(json); i++) {
      ushort c = StringGetCharacter(json, i);
      if(c == '{') depth++;
      if(c == '}' && depth > 0) { depth--; if(depth == 0) count++; }
   }
   return count;
}

string NthObject(string json, int n) {
   int found = 0, depth = 0, start = -1;
   for(int i = 0; i < StringLen(json); i++) {
      ushort c = StringGetCharacter(json, i);
      if(c == '{') { depth++; if(depth == 1) start = i; }
      if(c == '}' && depth > 0) {
         depth--;
         if(depth == 0 && start >= 0) {
            if(found == n) return StringSubstr(json, start, i - start + 1);
            found++; start = -1;
         }
      }
   }
   return "";
}

string GetField(string obj, string key) {
   string search = "\"" + key + "\"";
   int pos = StringFind(obj, search);
   if(pos < 0) return "";
   pos += StringLen(search);
   while(pos < StringLen(obj) && StringGetCharacter(obj, pos) != ':') pos++;
   pos++;
   while(pos < StringLen(obj) && StringGetCharacter(obj, pos) == ' ') pos++;
   if(pos >= StringLen(obj)) return "";
   ushort c = StringGetCharacter(obj, pos);
   if(c == '"') {
      int s = pos + 1, e = StringFind(obj, "\"", s);
      return (e > s) ? StringSubstr(obj, s, e - s) : "";
   }
   int s = pos;
   while(pos < StringLen(obj)) {
      ushort ch = StringGetCharacter(obj, pos);
      if(ch == ',' || ch == '}' || ch == ' ') break;
      pos++;
   }
   return StringSubstr(obj, s, pos - s);
}

//-- HTTP helpers -----------------------------------------------------
string VpsGet(string path) {
   char   post[], resp[];
   string respHdr;
   string headers = "X-Bridge-Token: " + InpToken + "\r\n";
   int ret = WebRequest("GET", InpVpsUrl + path, headers, 15000, post, resp, respHdr);
   if(ret < 0) {
      Print("Edgekit WebRequest failed (", path, "): error ", GetLastError(),
            ". Add '", InpVpsUrl, "' in Tools→Options→Expert Advisors→Allow WebRequest");
      return "";
   }
   return CharsToStr(resp);
}

string VpsPost(string path, string body) {
   char post[], resp[];
   StrToChars(body, post);
   string respHdr;
   string headers = "X-Bridge-Token: " + InpToken + "\r\nContent-Type: application/json\r\n";
   int ret = WebRequest("POST", InpVpsUrl + path, headers, 15000, post, resp, respHdr);
   if(ret < 0) Print("Edgekit POST failed (", path, "): error ", GetLastError());
   return CharsToStr(resp);
}

//-- Order helpers ----------------------------------------------------
long OpenOrder(string symbol, string side, double volume, double sl, double tp) {
   MqlTradeRequest req = {};
   MqlTradeResult  res = {};
   if(!SymbolSelect(symbol, true)) { Print("Edgekit: symbol not found: ", symbol); return -1; }
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick)) { Print("Edgekit: no tick: ", symbol); return -1; }
   bool isBuy    = (side == "buy");
   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = symbol;
   req.volume    = volume;
   req.type      = isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price     = isBuy ? tick.ask : tick.bid;
   req.sl        = sl;
   req.tp        = tp;
   req.deviation = 20;
   req.magic     = MAGIC;
   req.comment   = "edgekit-fwd";
   req.type_time = ORDER_TIME_GTC;
   ENUM_ORDER_TYPE_FILLING modes[3] = {ORDER_FILLING_IOC, ORDER_FILLING_FOK, ORDER_FILLING_RETURN};
   for(int m = 0; m < 3; m++) {
      req.type_filling = modes[m];
      if(OrderSend(req, res) && res.retcode == TRADE_RETCODE_DONE) return res.order;
   }
   Print("Edgekit: order rejected retcode=", res.retcode, ": ", res.comment);
   return -1;
}

double ClosedProfit(long ticket) {
   HistorySelectByPosition(ticket);
   double p = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--) {
      ulong deal = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(deal, DEAL_POSITION_ID) == ticket)
         p += HistoryDealGetDouble(deal, DEAL_PROFIT)
            + HistoryDealGetDouble(deal, DEAL_COMMISSION)
            + HistoryDealGetDouble(deal, DEAL_SWAP);
   }
   return p;
}

//-- Poll & execute ---------------------------------------------------
void PollAndExecute() {
   string body = VpsGet("/forward/live/signals");
   if(body == "") return;

   // Report any closed positions first
   for(int i = 0; i < g_n; i++) {
      if(g_state[i].ticket < 0) continue;
      if(PositionSelectByTicket(g_state[i].ticket)) continue;  // still open
      double profit = ClosedProfit(g_state[i].ticket);
      string ev = StringFormat(
         "{\"action\":\"close\",\"ticket\":%d,\"profit\":%.2f,\"comment\":\"ek:%d\"}",
         g_state[i].ticket, profit, g_state[i].ft_id);
      VpsPost("/forward/" + IntegerToString(g_state[i].ft_id) + "/event", ev);
      Print("Edgekit ft=", g_state[i].ft_id, " closed ticket=", g_state[i].ticket, " P&L=", profit);
      g_state[i].ticket = -1;
   }

   // Process signals
   int n = CountObjects(body);
   for(int i = 0; i < n; i++) {
      string obj      = NthObject(body, i);
      if(obj == "") continue;
      long   ft_id    = (long)StringToInteger(GetField(obj, "ft_id"));
      string symbol   = GetField(obj, "symbol");
      string side     = GetField(obj, "side");
      double sl       = StringToDouble(GetField(obj, "sl"));
      double tp       = StringToDouble(GetField(obj, "tp"));
      double volume   = StringToDouble(GetField(obj, "volume"));
      string bar_time = GetField(obj, "bar_time");
      if(ft_id == 0 || symbol == "" || bar_time == "") continue;
      int idx = StateIdx(ft_id);
      if(idx < 0) continue;
      if(g_state[idx].last_bar == bar_time) continue;   // already acted
      if(g_state[idx].ticket >= 0) {
         if(PositionSelectByTicket(g_state[idx].ticket)) continue;   // still open
      }
      if(volume <= 0) volume = 0.01;
      long ticket = OpenOrder(symbol, side, volume, sl, tp);
      if(ticket < 0) continue;
      g_state[idx].ticket   = ticket;
      g_state[idx].last_bar = bar_time;
      MqlTick tick;
      SymbolInfoTick(symbol, tick);
      double fill   = (side == "buy") ? tick.ask : tick.bid;
      double spread = tick.ask - tick.bid;
      string ev = StringFormat(
         "{\"action\":\"open\",\"symbol\":\"%s\",\"side\":\"%s\","
         "\"volume\":%.2f,\"fill_price\":%.5f,\"spread\":%.5f,"
         "\"sl\":%.5f,\"tp\":%.5f,\"ticket\":%d,\"comment\":\"ek:%d\"}",
         symbol, side, volume, fill, spread, sl, tp, ticket, ft_id);
      VpsPost("/forward/" + IntegerToString(ft_id) + "/event", ev);
      Print("Edgekit ft=", ft_id, " opened ", StringUpperCase(side), " ",
            volume, " ", symbol, " @ ", fill,
            "  sl=", sl, "  tp=", tp, "  ticket=", ticket);
   }
}

//+------------------------------------------------------------------+
int OnInit() {
   if(InpToken == "") {
      Alert("Edgekit: token not set!\n\n"
            "Open EA Properties (F7) → Inputs → paste your token\n"
            "Get it at: https://edgekit.uk/resources  →  Connect your MT5");
      return INIT_FAILED;
   }
   string h = VpsGet("/healthz");
   if(StringFind(h, "\"ok\"") >= 0)
      Print("Edgekit: VPS connected ✓  polling every ", InpPollSecs, "s");
   else
      Print("Edgekit: WARNING — VPS not reachable. Check InpVpsUrl and WebRequest settings.");
   EventSetTimer(InpPollSecs);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); Print("Edgekit: connector stopped."); }
void OnTimer() { PollAndExecute(); }
void OnTick()  {}
//+------------------------------------------------------------------+
