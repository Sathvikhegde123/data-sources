import { useEffect, useState } from "react";

function SafeText({ value, className }) {
  if (!value) {
    return null;
  }
  return <p className={className}>{value}</p>;
}

function JsonBlock({ value }) {
  if (!value) {
    return null;
  }
  return <pre className="rag-json">{JSON.stringify(value, null, 2)}</pre>;
}

export default function RagDetailDrawer({ selection, apiBase, onClose }) {
  const [detail, setDetail] = useState(null);
  const [status, setStatus] = useState("idle");

  useEffect(() => {
    if (!selection) {
      setDetail(null);
      setStatus("idle");
      return;
    }

    const load = async () => {
      setStatus("loading");
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

  if (!selection) {
    return null;
  }

  const record = detail?.record || {};
  const parsed = detail?.parsed_json || {};
  const document = parsed.document || {};
  const structured = parsed.structured_data || {};
  const docType = document.document_type || record.document_type || "document";

  const caseMeta = structured.case_metadata || {};
  const actMeta = structured.act_metadata || {};
  const articleMeta = structured.article_metadata || {};

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
          <section>
            <h3>Document</h3>
            <div className="meta-grid">
              <span>Document key</span>
              <span>{document.doc_key || record.id || "-"}</span>
              <span>Type</span>
              <span>{docType}</span>
              <span>Source file</span>
              <span className="rag-path">{document.source_file || record.locations?.source_file || "-"}</span>
              <span>Parsed JSON</span>
              <span className="rag-path">{record.locations?.relative_path || "-"}</span>
            </div>
          </section>

          {record.summary ? (
            <section>
              <h3>RAG summary</h3>
              <p className="rag-text-block">{record.summary}</p>
            </section>
          ) : null}

          {docType === "case" ? (
            <section>
              <h3>Case metadata</h3>
              <div className="meta-grid">
                <span>Court</span>
                <span>{caseMeta.court || "-"}</span>
                <span>Citation</span>
                <span>{caseMeta.citation || "-"}</span>
                <span>Judgment date</span>
                <span>{caseMeta.date_of_judgment || "-"}</span>
                <span>Winner</span>
                <span>{caseMeta.winner_role || "-"}</span>
              </div>
              <SafeText className="rag-text-block" value={caseMeta.dispute_summary} />
              <SafeText className="rag-text-block" value={caseMeta.plain_english_translation} />
              <SafeText className="rag-text-block" value={caseMeta.verdict_order} />
            </section>
          ) : null}

          {docType === "act" ? (
            <section>
              <h3>Act metadata</h3>
              <div className="meta-grid">
                <span>Act number</span>
                <span>{actMeta.act_number || "-"}</span>
                <span>Enactment date</span>
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
              <h3>Article metadata</h3>
              <div className="meta-grid">
                <span>Article number</span>
                <span>{articleMeta.article_number || "-"}</span>
                <span>Status</span>
                <span>{articleMeta.status || "-"}</span>
                <span>Source</span>
                <span>{articleMeta.source_document || "-"}</span>
              </div>
            </section>
          ) : null}

          {parsed.raw_text ? (
            <section>
              <h3>Raw text</h3>
              <pre className="rag-text-block">{parsed.raw_text}</pre>
            </section>
          ) : null}

          <section>
            <h3>Full JSON</h3>
            <JsonBlock value={parsed} />
          </section>
        </div>
      )}
    </aside>
  );
}
