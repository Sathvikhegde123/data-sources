const filters = [
  { id: "article", label: "Articles" },
  { id: "act", label: "Acts" },
  { id: "case", label: "Cases" }
];

export default function Filters({ active, onChange }) {
  return (
    <div className="filters">
      {filters.map((filter) => (
        <button
          key={filter.id}
          type="button"
          className={`chip ${active === filter.id ? "active" : ""}`}
          onClick={() => onChange(filter.id)}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}
