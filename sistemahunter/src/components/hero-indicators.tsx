import { BarChart3, CheckCircle2, Target, TrendingUp } from 'lucide-react';

export function HeroIndicators() {
  return <div className="hero-indicators" aria-label="Indicadores de gestão demonstrativos">
    <div className="hero-indicator-window">
    <div className="hero-proof hero-metric hero-revenue">
      <div className="hero-proof-head"><BarChart3 size={15}/> Faturamento</div>
      <div className="hero-proof-label">Evolução mensal</div>
      <svg className="revenue-line" viewBox="0 0 160 52" aria-hidden="true">
        <path className="chart-grid" d="M0 16H160 M0 34H160 M0 51H160"/>
        <path className="chart-line" pathLength="1" d="M3 43 L28 36 L52 39 L78 23 L102 28 L129 12 L157 4"/>
      </svg>
    </div>
    <div className="hero-proof hero-pricing">
      <div className="hero-proof-head"><TrendingUp size={15}/> Precificação inteligente</div>
      <div className="hero-proof-label">Rentabilidade do orçamento</div>
      <div className="hero-proof-value">76,66% <span>Ótimo</span></div>
      <div className="mini-bars" aria-hidden="true"><i/><i/><i/><i/><i/><i/><i/></div>
    </div>
    <div className="hero-proof hero-metric hero-goals">
      <div className="hero-proof-head"><Target size={15}/> Metas da oficina</div>
      <div className="goal-summary">
        <div className="goal-ring"><svg viewBox="0 0 64 64" aria-hidden="true"><circle className="ring-track" cx="32" cy="32" r="27"/><circle className="ring-progress" cx="32" cy="32" r="27" pathLength="100"/></svg><strong>72%</strong></div>
        <div className="hero-proof-label">Acompanhamento<br/>das metas</div>
      </div>
    </div>
    <div className="hero-proof hero-metric hero-performance">
      <div className="hero-proof-head"><CheckCircle2 size={15}/> Desempenho</div>
      <div className="hero-proof-label">Aprovação de orçamentos</div>
      <div className="performance-value"><strong>68%</strong></div>
      <div className="performance-track" aria-hidden="true"><i/></div>
    </div>
    </div>
  </div>;
}