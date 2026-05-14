import { useEffect, useMemo, useState } from "react";
import Card from "./components/Card.jsx";
import DetailDrawer from "./components/DetailDrawer.jsx";
import Filters from "./components/Filters.jsx";
import RagDetailDrawer from "./components/RagDetailDrawer.jsx";

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

const ragEmptyState = {
  status: "idle",
  error: null,
  results: []
};

const clampText = (value, limit) => {
  if (!value) {
    return "";
  }
  if (value.length <= limit) {
    return value;
  }
  const slice = value.slice(0, Math.max(0, limit - 3));
  const lastSpace = slice.lastIndexOf(" ");
  const trimmed = lastSpace > 20 ? slice.slice(0, lastSpace) : slice;
  return `${trimmed}...`;
};

export default function App() {
  const [query, setQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const [casesState, setCasesState] = useState(emptyState);
  const [actsState, setActsState] = useState(emptyState);
  const [articlesState, setArticlesState] = useState(emptyState);
  const [ragQuery, setRagQuery] = useState("");
  const [ragState, setRagState] = useState(ragEmptyState);
  const [ragSelected, setRagSelected] = useState(null);

  const runRag = async () => {
    const trimmed = ragQuery.trim();
    if (!trimmed) {
      setRagState({
        status: "error",
        error: "Enter a scenario to run the RAG pipeline.",
        results: []
      });
      return;
    }

    setRagState({ status: "loading", error: null, results: [] });

    try {
      const response = await fetch(`${API_BASE}/rag`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed })
      });

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        throw new Error(errorPayload?.detail || "RAG request failed");
      }

      const payload = await response.json();
      setRagState({
        status: "ready",
        error: null,
        results: payload.results || []
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setRagState({ status: "error", error: message, results: [] });
    }
  };

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
      summary: clampText(
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
      summary: clampText(item.objective || item.extent_application || "", 220),
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

  const ragCards = useMemo(() => {
    return ragState.results.map((result) => {
      const scoreValue = Number(result.similarity_score);
      const scoreLabel = Number.isFinite(scoreValue)
        ? `Score ${scoreValue.toFixed(3)}`
        : "";
      return {
        id: result.id,
        type: result.document_type || "case",
        title: result.title || "Untitled",
        subtitle: result.court || "",
        meta: scoreLabel,
        summary: clampText(result.summary || result.full_text_preview || "", 220),
        tags: result.keywords || [],
        highlight: {},
        relativePath: result.relative_path || ""
      };
    });
  }, [ragState.results]);

  const filteredCards = useMemo(() => {
    const lowerQuery = query.trim().toLowerCase();
    return cards.filter((card) => {
      if (activeFilter && activeFilter !== "all" && card.type !== activeFilter) {
        return false;
      }
      if (!card.title || card.title.trim().length === 0) {
        return false;
      }
      const hasHighlight =
        card.highlight &&
        Object.values(card.highlight).some(
          (value) => value && value.toString().trim().length > 0
        );
      const hasContent =
        (card.subtitle && card.subtitle.trim().length > 0) ||
        (card.meta && card.meta.trim().length > 0) ||
        (card.summary && card.summary.trim().length > 0) ||
        (card.tags && card.tags.length > 0) ||
        hasHighlight;
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
  const ragStatusMessage =
    ragState.status === "loading"
      ? "Running RAG search..."
      : ragState.status === "error"
      ? "RAG request failed."
      : ragState.status === "ready"
      ? `${ragState.results.length} matches`
      : "Enter a scenario to run the RAG pipeline.";

  return (
    <div className="app">
      <div className="page-layout">
        <section className="rag-area">
          <div className="rag-panel">
            <div className="rag-header">
              <div>
                <p className="rag-eyebrow">RAG pipeline</p>
                <h2>Ask a property rights scenario</h2>
                <p className="rag-subtitle">
                  Provide a short description of your property dispute or question. The
                  pipeline returns the most relevant cases, acts, and articles.
                </p>
              </div>
              <div className="rag-badge">Semantic retrieval</div>
            </div>
            <div className="rag-input">
              <textarea
                className="rag-textarea"
                placeholder="Example: My neighbor claims the boundary line on the sale deed is incorrect..."
                rows={4}
                value={ragQuery}
                onChange={(event) => setRagQuery(event.target.value)}
              />
              <div className="rag-actions">
                <button
                  className="primary-button"
                  type="button"
                  onClick={runRag}
                  disabled={ragState.status === "loading"}
                >
                  {ragState.status === "loading" ? "Searching..." : "Run RAG"}
                </button>
                <span className="rag-status">{ragStatusMessage}</span>
              </div>
            </div>
          </div>

          <section className="rag-results">
            <div className="rag-results-header">
              <h3>RAG results</h3>
              {ragState.status === "ready" ? (
                <span className="rag-results-meta">
                  Showing {ragState.results.length} result
                  {ragState.results.length === 1 ? "" : "s"}
                </span>
              ) : null}
            </div>
            {ragState.status === "idle" && (
              <p className="rag-muted">Enter a scenario to see retrieval results.</p>
            )}
            {ragState.status === "error" && (
              <p className="rag-error">{ragState.error}</p>
            )}
            {ragState.status === "ready" && ragState.results.length === 0 && (
              <p className="rag-muted">No matching documents found.</p>
            )}
            {ragState.status === "ready" && ragCards.length > 0 ? (
              <div className="rag-grid">
                {ragCards.map((card) => (
                  <Card
                    key={`rag-${card.type}-${card.id}`}
                    card={card}
                    label={typeLabels[card.type] || "Document"}
                    onSelect={() =>
                      setRagSelected({
                        id: card.id,
                        type: card.type,
                        relativePath: card.relativePath
                      })
                    }
                  />
                ))}
              </div>
            ) : null}
          </section>
        </section>

        <section className="library-area">
          <header className="hero">
            <div className="hero-content">
              <p className="hero-eyebrow">Property Rights Intelligence</p>
              <h1>Legal cards that read like a briefing, not a wall of text.</h1>
              <p className="hero-subtitle">
                Search, filter, and open structured cards for cases, acts, and articles.
                Built for layman queries and legal research in one place.
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
        </section>
      </div>

      <DetailDrawer
        selection={selected}
        onClose={() => setSelected(null)}
        apiBase={API_BASE}
      />
      <RagDetailDrawer
        selection={ragSelected}
        onClose={() => setRagSelected(null)}
        apiBase={API_BASE}
      />
    </div>
  );
}
