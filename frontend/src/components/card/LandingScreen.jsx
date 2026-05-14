// frontend/src/components/card/LandingScreen.jsx
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCardStore } from '../../store/useCardStore.js';
import { BirthForm } from './BirthForm.jsx';
import { CardSkeleton } from './CardSkeleton.jsx';
import { track } from '../../lib/analytics.js';

export function LandingScreen() {
  const navigate = useNavigate();
  const { loading, error, submitBirth } = useCardStore();

  useEffect(() => {
    const from = new URLSearchParams(window.location.search).get('from') || 'direct';
    track('form_start', { from });
  }, []);

  async function handleSubmit() {
    const card = await submitBirth();
    if (card) {
      track('chart_create_success', {
        flow: 'card',
        type_id: card.type_id,
        share_slug: card.share_slug,
      });
      navigate(`/card/${card.share_slug}`);
    } else {
      track('chart_create_failed', { flow: 'card' });
    }
  }

  if (loading) return <CardSkeleton />;

  return (
    <main className="landing-screen">
      <header className="hero">
        <h1>有时</h1>
        <p className="tagline">3 秒看你的人格图鉴</p>
      </header>
      <BirthForm onSubmit={handleSubmit} />
      {error && <div className="form-error" role="alert">{error}</div>}
    </main>
  );
}
