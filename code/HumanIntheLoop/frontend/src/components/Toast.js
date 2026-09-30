import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import './Toast.css';

/**
 * Toast Context - 提供 4 种用法：
 *
 *   toast.show({ kind: 'info' | 'success' | 'warning' | 'error', message, ... })
 *   toast.success(msg), toast.error(msg), toast.warning(msg), toast.info(msg)
 *   toast.confirm({ title, message, confirmText, cancelText, danger })
 *        → 返回 Promise<boolean>
 */

const ToastContext = createContext(null);

let _id = 0;
const nextId = () => ++_id;

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const timers = useRef(new Map());

  const dismiss = useCallback((id) => {
    setItems((arr) => arr.filter((t) => t.id !== id));
    const tm = timers.current.get(id);
    if (tm) {
      clearTimeout(tm);
      timers.current.delete(id);
    }
  }, []);

  /** 内部：仅当 duration > 0 时才设置自动关闭 */
  const scheduleAutoDismiss = useCallback(
    (id, duration) => {
      if (!duration || duration <= 0) return;
      const timer = setTimeout(() => dismiss(id), duration);
      timers.current.set(id, timer);
    },
    [dismiss]
  );

  const show = useCallback(
    (opts) => {
      const id = nextId();
      const item = {
        id,
        kind: opts.kind || 'info',
        title: opts.title || '',
        message: opts.message || '',
        confirmText: opts.confirmText || '确定',
        cancelText: opts.cancelText || '取消',
        danger: !!opts.danger,
        actions: opts.actions || null, // 自定义按钮 [{label, onClick, primary?, danger?}]
        duration: opts.duration ?? (opts.kind === 'error' ? 5000 : 3500),
      };
      setItems((arr) => [...arr, item]);
      scheduleAutoDismiss(id, item.duration);
      return id;
    },
    [dismiss, scheduleAutoDismiss]
  );

  // confirm(): 在 toast 上显示「确认 / 取消」，返回 Promise<boolean>
  const confirm = useCallback(
    (opts) =>
      new Promise((resolve) => {
        const id = nextId();
        const item = {
          id,
          kind: opts.kind || 'warning',
          title: opts.title || '请确认',
          message: opts.message || '',
          confirmText: opts.confirmText || '确定',
          cancelText: opts.cancelText || '取消',
          danger: !!opts.danger,
          actions: [
            {
              label: opts.cancelText || '取消',
              onClick: () => {
                dismiss(id);
                resolve(false);
              },
            },
            {
              label: opts.confirmText || '确定',
              primary: true,
              danger: !!opts.danger,
              onClick: () => {
                dismiss(id);
                resolve(true);
              },
            },
          ],
          // confirm 不自动消失（duration=0）
          duration: 0,
        };
        setItems((arr) => [...arr, item]);
        // ★ 关键修复：duration=0 时不要再 setTimeout(..., 0)，否则会在下一帧立即关闭弹窗
        scheduleAutoDismiss(id, 0);
      }),
    [dismiss, scheduleAutoDismiss]
  );

  const value = useMemo(() => {
    const helper = (kind) => (msg, opts = {}) =>
      show({ kind, message: typeof msg === 'string' ? msg : '', ...opts });
    return {
      show,
      confirm,
      success: helper('success'),
      error: helper('error'),
      warning: helper('warning'),
      info: helper('info'),
      dismiss,
    };
  }, [show, confirm, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastContainer items={items} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast 必须在 <ToastProvider> 内使用');
  return ctx;
}

function ToastContainer({ items, onDismiss }) {
  return (
    <div className="toast-stack">
      {items.map((t) => (
        <ToastItem key={t.id} item={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

const ICONS = {
  info: 'ℹ️',
  success: '✅',
  warning: '⚠️',
  error: '❌',
};

function ToastItem({ item, onDismiss }) {
  const icon = ICONS[item.kind] || 'ℹ️';
  return (
    <div className={`toast-item toast-${item.kind} ${item.danger ? 'toast-danger' : ''}`}>
      <div className="toast-icon">{icon}</div>
      <div className="toast-body">
        {item.title && <div className="toast-title">{item.title}</div>}
        <div className="toast-message">{item.message}</div>
        {item.actions && item.actions.length > 0 && (
          <div className="toast-actions">
            {item.actions.map((a, i) => (
              <button
                key={i}
                className={
                  'btn btn-sm ' +
                  (a.danger
                    ? 'btn-danger'
                    : a.primary
                    ? 'btn-primary'
                    : 'btn-ghost')
                }
                onClick={a.onClick}
              >
                {a.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <button className="toast-close" onClick={() => onDismiss(item.id)} aria-label="关闭">
        ×
      </button>
    </div>
  );
}