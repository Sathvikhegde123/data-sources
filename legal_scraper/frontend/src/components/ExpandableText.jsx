import { useState } from "react";

function truncateAtWord(value, limit) {
  if (!value) {
    return "";
  }
  if (value.length <= limit) {
    return value;
  }
  const slice = value.slice(0, limit);
  const lastSpace = slice.lastIndexOf(" ");
  if (lastSpace > 20) {
    return slice.slice(0, lastSpace);
  }
  return slice;
}

export default function ExpandableText({ text, fallback, limit = 140 }) {
  const [expanded, setExpanded] = useState(false);
  const value = text || fallback;
  const canExpand = value && value.length > limit;
  const visibleText = canExpand && !expanded ? `${truncateAtWord(value, limit).trim()}...` : value;

  return (
    <div className="expandable-text">
      <p>{visibleText}</p>
      {canExpand ? (
        <button
          className="text-button"
          type="button"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? "Show less" : "Read more"}
        </button>
      ) : null}
    </div>
  );
}
