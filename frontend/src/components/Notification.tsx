import { useEffect } from 'react';
import { useAppStore } from '../store';

export function Notification() {
  const notification = useAppStore((state) => state.notification);
  const setNotification = useAppStore((state) => state.setNotification);

  useEffect(() => {
    if (!notification || notification.kind === 'error') return;
    const timer = window.setTimeout(() => setNotification(null), 3500);
    return () => window.clearTimeout(timer);
  }, [notification, setNotification]);

  if (!notification) return null;
  return (
    <div className={`toast ${notification.kind}`} role={notification.kind === 'error' ? 'alert' : 'status'}>
      <span aria-hidden="true">
        {notification.kind === 'error' ? '!' : notification.kind === 'success' ? '✓' : 'i'}
      </span>
      <p>{notification.message}</p>
      <button type="button" onClick={() => setNotification(null)} aria-label="Fermer le message">
        ×
      </button>
    </div>
  );
}
