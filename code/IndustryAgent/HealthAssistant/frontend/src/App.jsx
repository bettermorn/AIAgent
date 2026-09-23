import { useEffect, useRef, useState } from "react";
import PatientForm from "./components/PatientForm.jsx";
import AssistantMessage from "./components/AssistantMessage.jsx";
import { askQuestion, checkHealth } from "./api.js";

const EXAMPLES = [
  "头痛伴随发烧该如何处理？",
  "平时如何控制血压？",
  "我被诊断为 2 型糖尿病，饮食上要注意什么？",
];

const splitList = (s) =>
  s
    .split(/[,，]/)
    .map((x) => x.trim())
    .filter(Boolean);

function buildPatient(profile) {
  const patient = {};
  if (profile.age !== "") patient.age = Number(profile.age);
  if (profile.sex) patient.sex = profile.sex;
  const conditions = splitList(profile.conditions);
  const meds = splitList(profile.meds);
  const allergies = splitList(profile.allergies);
  if (conditions.length) patient.conditions = conditions;
  if (meds.length) patient.meds = meds;
  if (allergies.length) patient.allergies = allergies;
  return Object.keys(patient).length ? patient : null;
}

export default function App() {
  const [profile, setProfile] = useState({
    user_id: "user_web",
    age: "",
    sex: "",
    conditions: "",
    meds: "",
    allergies: "",
  });
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    checkHealth().then(setHealth);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async (text) => {
    const question = (text ?? input).trim();
    if (!question || loading) return;
    if (!profile.user_id.trim()) {
      alert("请先在左侧填写用户 ID");
      return;
    }

    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setLoading(true);

    try {
      const data = await askQuestion({
        question,
        user_id: profile.user_id.trim(),
        patient: buildPatient(profile),
      });
      setMessages((m) => [...m, { role: "assistant", data }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", error: e.message }]);
    } finally {
      setLoading(false);
    }
  };

  const onKeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="logo">✚</span>
          <div>
            <h1>健康智能助手</h1>
            <p className="sub">合规优先 · RAG + LLM</p>
          </div>
        </div>

        <PatientForm
          profile={profile}
          onChange={setProfile}
          health={health}
          onRefresh={() => checkHealth().then(setHealth)}
        />

        <div className="sidebar-footer">
          仅供教育演示，非医疗设备，不能替代专业医疗护理。
        </div>
      </aside>

      <main className="chat">
        <div className="chat-scroll">
          {messages.length === 0 && (
            <div className="empty">
              <div className="empty-icon">💬</div>
              <h2>您好，请问有什么可以帮您？</h2>
              <p>我会基于可信临床指南提供教育信息，不构成医疗诊断。</p>
              <div className="examples">
                {EXAMPLES.map((q) => (
                  <button key={q} onClick={() => send(q)}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) =>
            m.role === "user" ? (
              <div className="msg user" key={i}>
                <div className="msg-body">{m.text}</div>
              </div>
            ) : (
              <AssistantMessage key={i} data={m.data} error={m.error} />
            )
          )}

          {loading && (
            <div className="msg assistant">
              <div className="msg-body">
                <span className="typing">
                  <i /><i /><i />
                </span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="composer">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeydown}
            placeholder="描述您的健康问题…（Enter 发送，Shift+Enter 换行）"
            rows={1}
          />
          <button className="send-btn" onClick={() => send()} disabled={loading || !input.trim()}>
            {loading ? "思考中…" : "发送"}
          </button>
        </div>
      </main>
    </div>
  );
}
