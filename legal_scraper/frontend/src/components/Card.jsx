export default function Card({ card, label, onSelect }) {
  const highlight =
    card.highlight?.plaintiff_appellant ||
    card.highlight?.sections ||
    "Open full card";

  return (
    <button className={`card card-${card.type}`} onClick={onSelect} type="button">
      <div className="card-content">
        <div className="card-top">
          <span className="card-label">{label}</span>
          {card.meta ? <span className="card-meta">{card.meta}</span> : null}
        </div>
        <h3>{card.title}</h3>
        {card.subtitle ? <p className="card-subtitle">{card.subtitle}</p> : null}
        {card.summary ? <p className="card-summary">{card.summary}</p> : null}
        {card.tags && card.tags.length > 0 ? (
          <div className="card-tags">
            {card.tags.slice(0, 3).map((tag) => (
              <span key={tag} className="tag">
                {tag}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <div className="card-footer">
        <span className="card-highlight">{highlight}</span>
        <span className="card-cta">View details</span>
      </div>
    </button>
  );
}
