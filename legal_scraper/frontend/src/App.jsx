import { useEffect, useMemo, useState } from "react";
import Card from "./components/Card.jsx";
import DetailDrawer from "./components/DetailDrawer.jsx";
import Filters from "./components/Filters.jsx";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api";

const typeLabels = {
  case: "Case",
  act: "Act",
  article: "Article"
};

const emptyState = {
  status: "idle",
  error: null,
  data: []
};

export default function App() {
  const [query, setQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("article");
  const [selected, setSelected] = useState(null);
  const [casesState, setCasesState] = useState(emptyState);
  const [actsState, setActsState] = useState(emptyState);
  const [articlesState, setArticlesState] = useState(emptyState);

  useEffect(() => {
    const load = async () => {
      setCasesState({ status: "loading", error: null, data: [] });
      setActsState({ status: "loading", error: null, data: [] });
      setArticlesState({ status: "loading", error: null, data: [] });

      try {
        const [casesRes, actsRes, articlesRes] = await Promise.all([
          fetch(`${API_BASE}/cases`),
          fetch(`${API_BASE}/acts`),
          fetch(`${API_BASE}/articles`)
        ]);

        if (!casesRes.ok || !actsRes.ok || !articlesRes.ok) {
          throw new Error("Failed to fetch data from API");
        }

        const [cases, acts, articles] = await Promise.all([
          casesRes.json(),
          actsRes.json(),
          articlesRes.json()
        ]);

        setCasesState({ status: "ready", error: null, data: cases });
        setActsState({ status: "ready", error: null, data: acts });
        setArticlesState({ status: "ready", error: null, data: articles });
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        setCasesState({ status: "error", error: message, data: [] });
        setActsState({ status: "error", error: message, data: [] });
        setArticlesState({ status: "error", error: message, data: [] });
      }
    };

    load();
  }, []);

  const cards = useMemo(() => {
    const hasVisibleText = (value) => {
      if (!value) {
        return false;
      }
      return /[A-Za-z0-9]/.test(value);
    };

    const clamp = (value, limit) => {
      if (!value) {
        return "";
      }
      if (value.length <= limit) {
        return value;
      }
      return `${value.slice(0, Math.max(0, limit - 3))}...`;
    };

    const extractYear = (value) => {
      if (!value) {
        return null;
      }
      const match = value.match(/(19|20)\d{2}/);
      return match ? match[0] : null;
    };

    const compactMeta = (parts) => {
      const meta = parts.filter(Boolean).join(" | ");
      return meta && meta.length <= 120 ? meta : "";
    };

    const caseCards = casesState.data.map((item) => ({
      id: item.document_id,
      type: "case",
      title: item.title || "",
      subtitle: item.court || "",
      meta: compactMeta([item.citation, item.date_of_judgment]),
      summary: clamp(
        item.dispute_summary || item.plain_english_translation || "",
        220
      ),
      tags: item.keywords || [],
      highlight: item.parties || {}
    }));

    const actCards = actsState.data.map((item) => ({
      id: item.document_id,
      type: "act",
      title: item.title || "",
      subtitle: item.act_number || extractYear(item.title) || "",
      meta: compactMeta([
        item.enactment_date ? `Enacted ${item.enactment_date}` : null,
        item.status
      ]),
      summary: clamp(item.objective || item.extent_application || "", 220),
      tags: item.keywords || [],
      highlight: {
        sections: `${item.section_count || 0} sections`
      }
    }));

    const articleCards = articlesState.data.map((item) => ({
      id: item.document_id,
      type: "article",
      title: item.title || "",
      subtitle: item.source_document || "",
      meta: compactMeta([
        item.article_number ? `Article ${item.article_number}` : null,
        item.status
      ]),
      summary: item.source_document ? "Constitutional article overview" : "",
      tags: item.keywords || [],
      highlight: {}
    }));

    const deduped = [];
    const seen = new Set();
    for (const card of [...articleCards, ...actCards, ...caseCards]) {
      if (!hasVisibleText(card.title)) {
        continue;
      }
      const key = `${card.type}::${card.title.toLowerCase()}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      deduped.push(card);
    }
    return deduped;
  }, [casesState.data, actsState.data, articlesState.data]);

  const filteredCards = useMemo(() => {
    const lowerQuery = query.trim().toLowerCase();
    return cards.filter((card) => {
      if (activeFilter && activeFilter !== "all" && card.type !== activeFilter) {
        return false;
      }
      if (!card.title || card.title.trim().length === 0) {
        return false;
      }
      const hasContent =
        (card.subtitle && card.subtitle.trim().length > 0) ||
        (card.meta && card.meta.trim().length > 0) ||
        (card.summary && card.summary.trim().length > 0) ||
        (card.tags && card.tags.length > 0);
      if (!hasContent) {
        return false;
      }
      if (!lowerQuery) {
        return true;
      }
      const haystack = [
        card.title,
        card.subtitle,
        card.meta,
        card.summary,
        ...(card.tags || [])
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(lowerQuery);
    });
  }, [cards, query, activeFilter]);

  const status = [casesState, actsState, articlesState].some(
    (state) => state.status === "loading"
  )
    ? "loading"
    : [casesState, actsState, articlesState].some((state) => state.status === "error")
    ? "error"
    : "ready";

  const errorMessage = casesState.error || actsState.error || articlesState.error;

  return (
    <div className="app">
      <header className="hero">
        <div className="hero-content">
          <p className="hero-eyebrow">Property Rights Intelligence</p>
          <h1>Legal cards that read like a briefing, not a wall of text.</h1>
          <p className="hero-subtitle">
            Search, filter, and open structured cards for cases, acts, and articles. Built
            for layman queries and legal research in one place.
          </p>
          <div className="search-row">
            <input
              className="search-input"
              placeholder="Search disputes, statutes, sections, keywords"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button className="primary-button" type="button">
              Explore
            </button>
          </div>
        </div>
        <div className="hero-card">
          <div className="hero-card-label">Live data</div>
          <div className="hero-card-value">{cards.length} documents</div>
          <div className="hero-card-meta">Property rights only</div>
        </div>
      </header>

      <section className="controls">
        <Filters active={activeFilter} onChange={setActiveFilter} />
        <div className="status">
          {status === "loading" && "Loading property data..."}
          {status === "error" && `API error: ${errorMessage}`}
          {status === "ready" && `${filteredCards.length} results`}
        </div>
      </section>

      <section className="grid">
        {filteredCards.map((card) => (
          <Card
            key={`${card.type}-${card.id}`}
            card={card}
            label={typeLabels[card.type]}
            onSelect={() => setSelected({ id: card.id, type: card.type })}
          />
        ))}
      </section>

      <DetailDrawer
        selection={selected}
        onClose={() => setSelected(null)}
        apiBase={API_BASE}
      />
    </div>
  );
}
