import { useEffect, useState } from "react";

const typeMap = {
  case: "cases",
  act: "acts",
  article: "articles"
};

function ExpandableText({ text, fallback, limit = 140 }) {
  const [expanded, setExpanded] = useState(false);
  const value = text || fallback;
  const canExpand = value && value.length > limit;
  const visibleText = canExpand && !expanded ? `${value.slice(0, limit).trim()}...` : value;

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

export default function DetailDrawer({ selection, onClose, apiBase }) {
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
        const endpoint = `${apiBase}/${typeMap[selection.type]}/${selection.id}`;
        const response = await fetch(endpoint);
        if (!response.ok) {
          throw new Error("Failed to fetch detail");
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

  return (
    <aside className="drawer">
      <div className="drawer-header">
        <div>
          <p className="drawer-label">{selection.type}</p>
          <h2>{detail?.title || "Loading..."}</h2>
        </div>
        <button type="button" className="ghost-button" onClick={onClose}>
          Close
        </button>
      </div>

      {status === "loading" && <p className="drawer-muted">Loading details...</p>}
      {status === "error" && (
        <p className="drawer-muted">Unable to load details. Check the API server.</p>
      )}

      {status === "ready" && detail && (
        <div className="drawer-body">
          <KeywordList keywords={detail.keywords} />

          {selection.type === "case" && (
            <>
              <section>
                <h3>Case metadata</h3>
                <div className="meta-grid">
                  <span>Court</span>
                  <span>{detail.court || "Pending"}</span>
                  <span>Citation</span>
                  <div className="meta-value">
                    <ExpandableText text={detail.citation} fallback="Pending" limit={160} />
                  </div>
                  <span>Judgment date</span>
                  <span>{detail.date_of_judgment || "Pending"}</span>
                  <span>Winner</span>
                  <span>{detail.winner_role || "Pending"}</span>
                </div>
              </section>

              <section>
                <h3>Parties</h3>
                <p className="pill">
                  Plaintiff: {detail.parties?.plaintiff_appellant || "Pending"}
                </p>
                <p className="pill">
                  Defendant: {detail.parties?.defendant_respondent || "Pending"}
                </p>
              </section>

              {detail.judges?.length ? (
                <section>
                  <h3>Judges</h3>
                  <div className="section-list">
                    {detail.judges.map((judge) => (
                      <p className="pill" key={judge}>
                        {judge}
                      </p>
                    ))}
                  </div>
                </section>
              ) : null}

              <section>
                <h3>Case brief</h3>
                <div className="section-list">
                  <article>
                    <h4>Plain English</h4>
                    <ExpandableText
                      text={detail.plain_english_translation || detail.dispute_summary}
                      fallback="Plain English summary not captured yet."
                    />
                  </article>
                  <article>
                    <h4>Proceedings</h4>
                    <ExpandableText
                      text={detail.procedural_history}
                      fallback="Procedural history not captured yet."
                    />
                  </article>
                  <article>
                    <h4>Court reasoning</h4>
                    <ExpandableText
                      text={detail.court_reasoning}
                      fallback="Reasoning not captured yet."
                    />
                  </article>
                  <article>
                    <h4>Final order</h4>
                    <ExpandableText
                      text={detail.verdict_order}
                      fallback="Final order not captured yet."
                    />
                  </article>
                </div>
              </section>

              <section>
                <h3>Arguments</h3>
                {detail.arguments?.length ? (
                  <div className="section-list">
                    {detail.arguments.map((item, index) => (
                      <article key={`${item.role}-${index}`}>
                        <h4>{item.role === "defendant_respondent" ? "Defendant" : "Plaintiff"}</h4>
                        <ExpandableText text={item.argument} fallback="Argument text pending." />
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="drawer-muted">Arguments not captured yet.</p>
                )}
              </section>

              <section>
                <h3>Timeline</h3>
                {detail.timeline?.length ? (
                  <ul className="timeline">
                    {detail.timeline.map((event, index) => (
                      <li key={`${event.date}-${index}`}>
                        <span>{event.date || "Date"}</span>
                        <ExpandableText text={event.event} fallback="Event text pending." limit={220} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="drawer-muted">Timeline not captured yet.</p>
                )}
              </section>
            </>
          )}

          {selection.type === "act" && (
            <>
              <section>
                <h3>Act metadata</h3>
                <div className="meta-grid">
                  <span>Act number</span>
                  <span>{detail.act_number || "Pending"}</span>
                  <span>Enactment date</span>
                  <span>{detail.enactment_date || "Pending"}</span>
                  <span>Status</span>
                  <span>{detail.status || "Pending"}</span>
                </div>
              </section>

              <section>
                <h3>Objective</h3>
                <ExpandableText text={detail.objective} fallback="Objective not captured yet." />
              </section>

              <section>
                <h3>Sections</h3>
                {detail.sections?.length ? (
                  <div className="section-list">
                    {detail.sections.map((section, index) => (
                      <article key={`${section.section_number}-${index}`}>
                        <h4>
                          {section.section_number || "Section"} {section.section_title || ""}
                        </h4>
                        <ExpandableText text={section.original_text} fallback="Text pending" />
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="drawer-muted">Sections not captured yet.</p>
                )}
              </section>
            </>
          )}

          {selection.type === "article" && (
            <>
              <section>
                <h3>Article metadata</h3>
                <div className="meta-grid">
                  <span>Article number</span>
                  <span>{detail.article_number || "Pending"}</span>
                  <span>Status</span>
                  <span>{detail.status || "Pending"}</span>
                  <span>Source</span>
                  <span>{detail.source_document || "Pending"}</span>
                </div>
              </section>

              <section>
                <h3>Original text</h3>
                <ExpandableText text={detail.original_text} fallback="Text not captured yet." />
              </section>

              <section>
                <h3>Amendments</h3>
                {detail.amendments?.length ? (
                  <ul className="amendments">
                    {detail.amendments.map((item, index) => (
                      <li key={`${item.amendment}-${index}`}>
                        <strong>{item.amendment}</strong>
                        <ExpandableText text={item.effect} fallback="Effect pending." limit={260} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="drawer-muted">Amendments not captured yet.</p>
                )}
              </section>

              <section>
                <h3>Editorial commentary</h3>
                <ExpandableText
                  text={detail.editorial_commentary}
                  fallback="Commentary not captured yet."
                />
              </section>
            </>
          )}
        </div>
      )}
    </aside>
  );
}
