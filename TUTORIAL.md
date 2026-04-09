# 📚 Tutorial: ReAct Agent and n8n Orchestration

Welcome to the comprehensive setup tutorial. This technical document explains the underlying architecture dynamics and how to successfully hook this FastAPI agent layer directly into your n8n workflows.

---

## 🇹🇷 Türkçe Eğitim (Turkish)

### 1. Sistem Mimarisi Nasıl Çalışıyor?
Bu sistem **ReAct (Reasoning and Acting)** konseptiyle çalışır. LLM'e (Büyük Dil Modeline) doğrudan görev yaptırmak yerine onun önce düşünmesini, karar vermesini ve kodlanmış deterministik araçları (**Tools**) sürece katmasını sağlar. 

Siz FastAPI `/chat` endpointi üzerinden bir ürün veya soru sorduğunuzda, LangGraph motoru şu adımları izler:
1. N8n üzerinden gelen mesajınız **State** (Konuşma Hafızası) içerisine eklenir. `trim_messages` kuralı sayesinde API maliyetlerinizi korumak için toplam hafıza hiçbir zaman **4000 token** sınırını aşmaz.
2. Ajan, verdiğimiz çok katı "System Prompt" (Sistem Kısıtlamaları / Guardrails) kurallarını okur. Eğer soru stok/tedarik ile ilgiliyse ve bir ürün adı içeriyorsa `calculate_inventory_risk` aracını (Tool) çağırmaya karar verir.
3. Arka planda çalıştırılan asenkron Node aracı, Read-Only SQLite veritabanına giderek dinamik risk analizi yapar ve bunu formatlı bir JSON olarak LLM'e geri yollar.
4. LLM bu ham risk skorlarını alıp yorumlayarak pürüzsüz bir dille size Nihai Cevabı (Final Message) aktarır.

### 2. n8n Entegrasyonu İçin Hayati İpuçları (Faz 6)
Bu sistemi n8n orkestrasyonunda konumlandırmak son derece sezgiseldir. n8n üzerinden bir **HTTP Request Node** kullanmanız yeterlidir.

* **Method:** `POST`
* **URL:** `http://localhost:8000/chat` (Geliştirici bulut ortamındaysa ilgili Public IP adresi)
* **Body Structure:** 
```json
{
  "user_id": "{{$json.chatSessionId}}",
  "message": "{{$json.userText}}"
}
```

🚨 **Kritik n8n Ayarı (Timeout - Zaman Aşımı):** 
ReAct ajanlarının LLM bazlı akılları ve veritabanı okumaları dış çağrılara (OpenAI vb.) bağlıdır. Eğer LLM 3 defa döngüye girerse bu süre saniyeler sürebilir. N8n'deki HTTP Request nodunun ayarlarına (Settings / Options) tıklayarak **Timeout** baz süresini en az **60000 ms (60 saniye)** olarak değiştirin. Aksi halde Node aceleci davranıp cevap gelmeden akışı hata ile kıracaktır.

* **IF (Koşul) Node Dalgalandırması:** 
LangGraph'ın standart karmaşık array yapısı içinden veri ayıklamak n8n tarafında kabus olmasın diye FastApi root JSON değerlerinde `risk_level` değerini direkt iletiyor. N8n arayüzünde `{{ $json.risk_level }}` diyerek "Eğer durum 'High' ise Slack'e mesaj at, değilse e-posta at" tarzında kolay akışlar kurgulayabilirsiniz.

---

## 🇬🇧 English Tutorial

### 1. How the Architecture Works
This system runs on the **ReAct (Reasoning and Acting)** principle. When you ask a question (`/chat` POST endpoint), the LangGraph cognitive engine processes it as follows:
1. The incoming message is appended to the agent's **State** (`SqliteSaver` persistent memory mapped to `thread_id`). A `trim_messages` mechanism ensures the context window never exceeds a safe 4,000 tokens (API cost optimization strategy).
2. The Agent reads the strict system prompt guardrails. If the user requests an inventory status, the agent decides to invoke the `calculate_inventory_risk` tool automatically.
3. The Tool queries the Read-Only SQLite database, dynamically analyzes stock thresholds vs sale velocities, and feeds logic-heavy JSON results back to the LLM agent node.
4. The LLM effortlessly translates this raw parsed analysis into a human-readable format as the final answer.

### 2. n8n Orchestration Tips (Phase 6)
To orchestrate this API layer via an n8n webhook, simply create an **HTTP Request Node**.

* **Method:** `POST`
* **URL:** `http://localhost:8000/chat`
* **Body Structure (JSON):** 
```json
{
  "user_id": "{{$json.chatId}}",
  "message": "{{$json.userText}}"
}
```

🚨 **Critical n8n Setting (Timeout Guardrail):** 
ReAct agents take time to reason, call tools, and fetch completions from OpenAI. Under the Options/Settings tab of your n8n HTTP Request Node, aggressively ensure you increase the **Timeout limit** to at least **60000 ms (60 seconds)**. Failure to do so will prematurely interrupt the agent cycle causing the n8n pipeline to collapse.

* **IF-Node Branching Strategy:** 
Extracting deeply nested keys in n8n UI mappings can be frustrating. To make integrations easier, our FastAPI automatically hoists the `risk_level` variable directly at the top level of the JSON response payload. You can directly extract `{{ $json.risk_level }} == 'High'` in n8n's Switch/IF node branches to trigger exact conditional logic natively.
