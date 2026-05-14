import { useEffect, useState } from "react";
import ExpandableText from "./ExpandableText.jsx";

function SafeText({ value, className }) {
  if (!value) {
    return null;
  }
  return <p className={className}>{value}</p>;
}

function KeywordList({ keywords }) {
  if (!keywords?.length) {
    return null;
  }

  return (
    <section>
      <h3>Keywords</h3>
      <div className="detail-tags">
        {keywords.map((keyword, index) => (
          <span className="tag" key={`${keyword}-${index}`}>
            {keyword}
          </span>
        ))}
      </div>
    </section>
  );
}

export default function RagDetailDrawer({ selection, apiBase, onClose, query }) {
  const [detail, setDetail] = useState(null);
  const [status, setStatus] = useState("idle");
  const [explanation, setExplanation] = useState(null);
  const [explainLoading, setExplainLoading] = useState(false);

  useEffect(() => {
    if (!selection) {
      setDetail(null);
      setStatus("idle");
      return;
    }

    const load = async () => {
      setStatus("loading");
      setExplanation(null);
      try {
        const response = await fetch(`${apiBase}/rag/records/${selection.id}`);
        if (!response.ok) {
          throw new Error("Failed to fetch RAG detail");
        }
        const data = await response.json();
        setDetail(data);
        setStatus("ready");
      } catch (error) {
        setStatus("error");
      }
    };

    load();
  }, [selection, apiBase]);

  const handleExplain = async () => {
    if (!detail || explainLoading) return;
    
    setExplainLoading(true);
    try {
      const response = await fetch(`${apiBase}/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query,
          document_title: detail.record?.title || detail.parsed_json?.document?.title,
          document_summary: detail.record?.summary,
          case_metadata: detail.parsed_json?.structured_data?.case_metadata,
          full_document: detail.parsed_json
        })
      });

      if (!response.ok) {
        throw new Error("Failed to generate explanation");
      }

      const data = await response.json();
      setExplanation(data.explanation);
    } catch (error) {
      setExplanation("Unable to generate explanation. Please try again.");
    } finally {
      setExplainLoading(false);
    }
  };

  if (!selection) {
    return null;
  }

  const record = detail?.record || selection || {};
  const parsed = detail?.parsed_json || {};
  const document = parsed.document || {};
  const structured = parsed.structured_data || {};
  const docType = document.document_type || record.document_type || "document";
  const similarityScore = selection?.similarityScore || record.similarity_score || 0;

  const caseMeta = structured.case_metadata || {};
  const actMeta = structured.act_metadata || {};
  const articleMeta = structured.article_metadata || {};

  const caseSections = parsed.raw_text
    ? parsed.raw_text.split(/\n+/).filter((value) => value.trim().length > 0)
    : [];

  return (
    <aside className="drawer">
      <div className="drawer-header">
        <div>
          <p className="drawer-label">RAG {docType}</p>
          <h2>{document.title || record.title || "Document"}</h2>
        </div>
        <button type="button" className="ghost-button" onClick={onClose}>
          Close
        </button>
      </div>

      {status === "loading" && <p className="drawer-muted">Loading RAG details...</p>}
      {status === "error" && (
        <p className="drawer-muted">Unable to load the RAG document. Check the API.</p>
      )}

      {status === "ready" && (
        <div className="drawer-body">
          <section className="relevance-section">
            <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginBottom: "1rem" }}>
              <div>
                <h3>Relevance Score</h3>
                <p style={{ margin: "0.5rem 0" }}>
                  <strong>{Number.isFinite(similarityScore) ? (similarityScore * 100).toFixed(1) : "N/A"}%</strong> match
                </p>
              </div>
              <button
                className="primary-button"
                onClick={handleExplain}
                disabled={explainLoading}
                style={{ marginLeft: "auto" }}
              >
                {explainLoading ? "Generating..." : "Explain Relevance"}
              </button>
            </div>
          </section>

          {explanation && (
            <section style={{ backgroundColor: "#f0f7ff", padding: "1rem", borderRadius: "4px", marginBottom: "1.5rem" }}>
              <h3>How it's relevant:</h3>
              <p>{explanation}</p>
            </section>
          )}

          <KeywordList keywords={record.keywords || []} />

          {record.summary ? (
            <section>
              <h3>RAG Summary</h3>
              <p className="rag-text-block">{record.summary}</p>
            </section>
          ) : null}

          {docType === "case" ? (
            <>
              <section>
                <h3>Case Metadata</h3>
                <div className="meta-grid">
                  <span>Court</span>
                  <span>{caseMeta.court || record.court || "-"}</span>
                  <span>Citation</span>
                  <div className="meta-value">
                    <ExpandableText 
                      text={caseMeta.citation || record.citation} 
                      fallback="Pending" 
                      limit={160} 
                    />
                  </div>
                  <span>Judgment date</span>
                  <span>{caseMeta.date_of_judgment || record.judgment_date || "-"}</span>
                  <span>Winner</span>
                  <span>{caseMeta.winner_role || record.verdict || "-"}</span>
                </div>
              </section>

              {record.parties && record.parties.length > 0 && (
                <section>
                  <h3>Parties</h3>
                  {record.parties.map((party, index) => (
                    <p className="pill" key={index}>
                      {party.role}: {party.name}
                    </p>
                  ))}
                </section>
              )}

              <section>
                <h3>Case Brief</h3>
                <div className="section-list">
                  {caseMeta.dispute_summary && (
                    <article>
                      <h4>Dispute Summary</h4>
                      <ExpandableText
                        text={caseMeta.dispute_summary}
                        fallback="Summary not available."
                      />
                    </article>
                  )}
                  {caseMeta.plain_english_translation && (
                    <article>
                      <h4>Plain English</h4>
                      <ExpandableText
                        text={caseMeta.plain_english_translation}
                        fallback="Plain English summary not available."
                      />
                    </article>
                  )}
                  {caseMeta.verdict_order && (
                    <article>
                      <h4>Verdict</h4>
                      <ExpandableText
                        text={caseMeta.verdict_order}
                        fallback="Verdict not available."
                      />
                    </article>
                  )}
                </div>
              </section>

              {record.legal_principles && record.legal_principles.length > 0 && (
                <section>
                  <h3>Legal Principles</h3>
                  <div className="section-list">
                    {record.legal_principles.map((principle, index) => (
                      <article key={index}>
                        <ExpandableText text={principle} fallback="Principle pending" limit={400} />
                      </article>
                    ))}
                  </div>
                </section>
              )}

              {caseSections.length > 0 && (
                <section>
                  <h3>Case Sections</h3>
                  <div className="section-list">
                    {caseSections.slice(0, 5).map((sectionText, index) => (
                      <article key={`case-section-${index}`}>
                        <ExpandableText text={sectionText} fallback="Text pending" limit={400} />
                      </article>
                    ))}
                  </div>
                </section>
              )}
            </>
          ) : null}

          {docType === "act" ? (
            <section>
              <h3>Act Metadata</h3>
              <div className="meta-grid">
                <span>Act Number</span>
                <span>{actMeta.act_number || "-"}</span>
                <span>Enactment Date</span>
                <span>{actMeta.enactment_date || "-"}</span>
                <span>Status</span>
                <span>{actMeta.status || "-"}</span>
              </div>
              <SafeText className="rag-text-block" value={actMeta.objective} />
              <SafeText className="rag-text-block" value={actMeta.extent_application} />
            </section>
          ) : null}

          {docType === "article" ? (
            <section>
              <h3>Article Metadata</h3>
              <div className="meta-grid">
                <span>Article Number</span>
                <span>{articleMeta.article_number || "-"}</span>
                <span>Status</span>
                <span>{articleMeta.status || "-"}</span>
                <span>Source</span>
                <span>{articleMeta.source_document || "-"}</span>
              </div>
            </section>
          ) : null}

          {parsed.raw_text && (
            <section>
              <h3>Raw Text</h3>
              <pre className="rag-text-block">{parsed.raw_text.substring(0, 1000)}...</pre>
            </section>
          )}
        </div>
      )}
    </aside>
  );
}
