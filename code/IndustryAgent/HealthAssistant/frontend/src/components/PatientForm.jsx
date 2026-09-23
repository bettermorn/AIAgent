import { useState } from "react";

export default function PatientForm({ profile, onChange, health, onRefresh }) {
  const [open, setOpen] = useState(false);

  const set = (key) => (e) => onChange({ ...profile, [key]: e.target.value });

  return (
    <div className="patient-panel">
      <div className="panel-row">
        <label>
          用户 ID
          <input
            value={profile.user_id}
            onChange={set("user_id")}
            placeholder="例如 user_123"
          />
        </label>
      </div>

      <button className="toggle-btn" onClick={() => setOpen(!open)}>
        {open ? "收起" : "填写"}患者信息（可选）
        <span className="arrow">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="patient-fields">
          <div className="grid-2">
            <label>
              年龄
              <input
                type="number"
                min="0"
                max="120"
                value={profile.age}
                onChange={set("age")}
                placeholder="35"
              />
            </label>
            <label>
              性别
              <select value={profile.sex} onChange={set("sex")}>
                <option value="">不指定</option>
                <option value="female">女</option>
                <option value="male">男</option>
                <option value="other">其他</option>
              </select>
            </label>
          </div>
          <label>
            已知疾病（逗号分隔）
            <input
              value={profile.conditions}
              onChange={set("conditions")}
              placeholder="高血压, 糖尿病"
            />
          </label>
          <label>
            用药（逗号分隔）
            <input
              value={profile.meds}
              onChange={set("meds")}
              placeholder="二甲双胍"
            />
          </label>
          <label>
            过敏史（逗号分隔）
            <input
              value={profile.allergies}
              onChange={set("allergies")}
              placeholder="青霉素"
            />
          </label>
        </div>
      )}

      <button
        className={`health-dot ${health ? "on" : "off"}`}
        onClick={onRefresh}
        title={health ? "后端在线" : "后端离线，点击重试"}
      >
        <span className="dot" />
        {health ? "服务在线" : "服务离线"}
      </button>
    </div>
  );
}
