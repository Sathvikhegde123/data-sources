
"""
Legal Property Rights RAG Pipeline
====================================
A retrieval-augmented generation system for Indian property law documents.
Uses TF-IDF + Cosine Similarity for semantic document retrieval.

Author: AI Assistant
Date: 2026-05-14
"""

import json
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import re
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from dataclasses import dataclass, field

@dataclass
class RetrievedDocument:
    """Structured result for retrieved documents"""
    rank: int
    id: str
    title: str
    document_type: str
    similarity_score: float
    keywords: List[str] = field(default_factory=list)
    summary: str = ""
    court: str = ""
    judgment_date: str = ""
    citation: str = ""
    parties: List[Dict] = field(default_factory=list)
    verdict: str = ""
    legal_principles: List[str] = field(default_factory=list)
    relevant_sections: List[str] = field(default_factory=list)
    full_text_preview: str = ""
    stats: Dict = field(default_factory=dict)
    relative_path: str = ""
    source_file: str = ""

    def to_dict(self) -> Dict:
        return {
            'rank': self.rank,
            'id': self.id,
            'title': self.title,
            'document_type': self.document_type,
            'similarity_score': round(self.similarity_score, 4),
            'keywords': self.keywords,
            'summary': self.summary,
            'court': self.court,
            'judgment_date': self.judgment_date,
            'citation': self.citation,
            'parties': self.parties,
            'verdict': self.verdict,
            'legal_principles': self.legal_principles,
            'relevant_sections': self.relevant_sections,
            'full_text_preview': self.full_text_preview,
            'stats': self.stats,
            'relative_path': self.relative_path,
            'source_file': self.source_file
        }

class LegalPropertyRAG:
    """
    Production-ready RAG Pipeline for Indian Property Law Documents

    Features:
    - TF-IDF + Cosine Similarity retrieval
    - Keyword boosting for legal terms
    - Document type filtering
    - Relevance scoring with confidence levels
    - Legal principle extraction
    """

    STOPWORDS = {
        'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
        'from', 'up', 'about', 'into', 'through', 'during', 'before', 'after', 'above', 'below',
        'between', 'among', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'shall', 'should', 'can', 'could', 'may', 'might',
        'must', 'this', 'that', 'these', 'those', 'i', 'me', 'my', 'myself', 'we', 'our', 'ours',
        'ourselves', 'you', 'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself',
        'she', 'her', 'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs',
        'themselves', 'what', 'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how',
        'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
        'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'now', 'then', 'here',
        'there', 'also', 'as', 'if', 'because', 'until', 'while', 'once', 'since', 'although',
        'though', 'unless', 'whether', 'however', 'therefore', 'thus', 'hence', 'accordingly',
        'consequently', 'nevertheless', 'nonetheless', 'meanwhile', 'furthermore', 'moreover',
        'besides', 'otherwise', 'instead', 'likewise', 'similarly', 'according', 'regarding',
        'concerning', 'respecting', 'notwithstanding', 'provided', 'section', 'act', 'court',
        'case', 'suit', 'appeal', 'judgment', 'order', 'decree', 'plaintiff', 'defendant',
        'appellant', 'respondent', 'petitioner', 'party', 'parties', 'bench', 'author',
        'equivalent', 'citations', 'citation', 'tags', 'queries', 'related', 'top', 'ai',
        'page', 'doc', 'uploaded', 'downloaded', 'file', 'no', 'nos', 'vs', 'versus',
        'etc', 'viz', 'ie', 'eg', 'hereinafter', 'whereas', 'wherein',
        'whereby', 'whereupon', 'therein', 'thereof', 'thereto', 'thereby', 'therefrom',
        'thereunder', 'therewith', 'herein', 'hereof', 'hereto', 'hereby', 'hereunder',
        'herewith', 'aforesaid', 'aforementioned', 'abovementioned', 'said', 'same', 'such',
        'supra', 'infra', 'per', 'curiam', 'honble', 'honourable', 'learned',
        'counsel', 'advocate', 'pleader', 'attorney', 'solicitor', 'barrister',
        'judge', 'justice', 'magistrate', 'tribunal', 'commission', 'committee',
        'board', 'authority', 'government', 'state', 'union', 'ministry', 'department',
        'notification', 'gazette', 'official', 'published', 'registered', 'registration',
        'register', 'book', 'index', 'volume', 'edition', 'report', 'reports',
        'law', 'legal', 'statute', 'enactment', 'legislation', 'provision', 'provisions',
        'clause', 'subclause', 'subsection', 'paragraph', 'schedule', 'appendix', 'annexure',
        'article', 'amendment', 'amended', 'repealed', 'inserted', 'substituted', 'omitted',
        'deleted', 'added', 'modified', 'altered', 'changed', 'made', 'done', 'taken',
        'given', 'granted', 'allowed', 'dismissed', 'rejected', 'accepted', 'approved',
        'confirmed', 'set', 'aside', 'upheld', 'overruled', 'reversed', 'modified',
        'varied', 'enhanced', 'reduced', 'increased', 'decreased', 'awarded', 'granted',
        'imposed', 'levied', 'charged', 'paid', 'payable', 'due', 'owing', 'outstanding',
        'arrears', 'balance', 'amount', 'sum', 'money', 'rupees', 'rs', 'costs', 'fees',
        'expenses', 'charges', 'damages', 'compensation', 'penalty', 'fine', 'interest',
        'principal', 'total', 'aggregate', 'net', 'gross', 'whole', 'part', 'portion',
        'share', 'proportion', 'ratio', 'percentage', 'per', 'cent', 'half', 'quarter',
        'third', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
        'ten', 'first', 'second', 'third', 'fourth', 'fifth', 'last', 'final', 'ultimate',
        'date', 'day', 'month', 'year', 'time', 'period', 'duration', 'term', 'tenure',
        'age', 'old', 'new', 'early', 'late', 'former', 'latter', 'previous', 'prior',
        'subsequent', 'following', 'next', 'coming', 'pending', 'ongoing', 'current',
        'present', 'existing', 'past', 'future', 'immediate', 'direct', 'indirect',
        'express', 'implied', 'tacit', 'explicit', 'implicit', 'absolute', 'relative',
        'conditional', 'unconditional', 'qualified', 'unqualified', 'limited', 'unlimited',
        'restricted', 'unrestricted', 'partial', 'full', 'complete', 'incomplete',
        'entire', 'total', 'whole', 'sole', 'exclusive', 'joint', 'common', 'mutual',
        'reciprocal', 'several', 'respective', 'collective', 'individual', 'personal',
        'private', 'public', 'general', 'special', 'specific', 'particular', 'certain',
        'uncertain', 'definite', 'indefinite', 'fixed', 'variable', 'constant',
        'permanent', 'temporary', 'provisional', 'interim', 'preliminary', 'final',
        'conclusive', 'inclusive', 'exclusive', 'additional', 'extra', 'supplementary',
        'subsidiary', 'ancillary', 'incidental', 'consequential', 'collateral',
        'material', 'immaterial', 'relevant', 'irrelevant', 'pertinent', 'impertinent',
        'applicable', 'inapplicable', 'appropriate', 'inappropriate', 'suitable',
        'unsuitable', 'proper', 'improper', 'valid', 'invalid', 'effective', 'ineffective',
        'operative', 'inoperative', 'binding', 'nonbinding', 'mandatory', 'directory',
        'permissive', 'prohibitory', 'compulsory', 'optional', 'discretionary',
        'obligatory', 'voluntary', 'peremptory', 'imperative',
        'advisory', 'recommendatory', 'suggestive', 'indicative', 'illustrative',
        'explanatory', 'descriptive', 'narrative', 'prescriptive', 'proscriptive',
        'affirmative', 'negative', 'positive', 'neutral', 'active', 'passive', 'direct',
        'indirect', 'immediate', 'remote', 'proximate', 'ultimate', 'primary', 'secondary',
        'tertiary', 'principal', 'subsidiary', 'main', 'auxiliary', 'accessory',
        'subordinate', 'dominant', 'servient', 'senior', 'junior', 'superior', 'inferior',
        'equal', 'unequal', 'equivalent', 'analogous', 'similar', 'dissimilar',
        'identical', 'different', 'same', 'opposite', 'contrary', 'contradictory',
        'conflicting', 'consistent', 'inconsistent', 'compatible', 'incompatible',
        'harmonious', 'disharmonious', 'consonant', 'dissonant', 'congruent',
        'incongruent', 'coextensive', 'coordinate', 'subordinate', 'parallel',
        'perpendicular', 'convergent', 'divergent', 'concurrent', 'consecutive',
        'successive', 'simultaneous', 'contemporaneous', 'synchronous', 'asynchronous',
        'concomitant', 'attendant', 'accompanying', 'incidental', 'consequential',
        'resulting', 'ensuing', 'following', 'subsequent', 'sequent',
        'preceding', 'antecedent', 'prior', 'previous', 'foregoing', 'aforementioned',
        'aforesaid', 'abovementioned', 'above', 'below', 'under', 'over', 'upon',
        'beneath', 'underneath', 'within', 'without', 'inside', 'outside', 'interior',
        'exterior', 'internal', 'external', 'inner', 'outer', 'inward', 'outward',
        'upward', 'downward', 'forward', 'backward', 'ahead', 'behind', 'before',
        'after', 'beyond', 'across', 'along', 'around', 'about', 'against', 'among',
        'amid', 'amidst', 'beside', 'besides', 'between', 'betwixt',
        'but', 'by', 'concerning', 'considering', 'despite', 'during', 'except',
        'excepting', 'excluding', 'following', 'like', 'minus', 'near', 'next',
        'notwithstanding', 'off', 'on', 'onto', 'opposite', 'out', 'outside',
        'over', 'past', 'pending', 'per', 'plus', 'regarding', 'round', 'save',
        'since', 'than', 'through', 'throughout', 'till', 'to', 'toward', 'towards',
        'under', 'underneath', 'unlike', 'until', 'up', 'upon', 'versus', 'via',
        'with', 'within', 'without', 'worth'
    }

    LEGAL_KEYWORDS = {
        'sale deed', 'registered', 'registration', 'title', 'ownership', 'possession',
        'boundary', 'encroachment', 'survey', 'measurement', 'plot', 'land',
        'mutation', 'revenue records', 'khasra', 'jamabandi', 'patta',
        'lease', 'tenancy', 'eviction', 'rent', 'landlord', 'tenant',
        'mortgage', 'charge', 'lien', 'hypothecation', 'pledge',
        'gift', 'will', 'testament', 'succession', 'inheritance', 'heir',
        'partition', 'coparcenary', 'joint family', 'ancestral property',
        'easement', 'right of way', 'access', 'light', 'air',
        'specific performance', 'injunction', 'damages', 'compensation',
        'adverse possession', 'prescription', 'limitation', 'time bar',
        'fraud', 'misrepresentation', 'undue influence', 'coercion',
        'benami', 'proxy', 'nominee', 'beneficial owner',
        'stamp duty', 'court fee', 'process fee', 'execution',
        'civil procedure', 'evidence', 'appeal', 'revision', 'review',
        'supreme court', 'high court', 'district court', 'tribunal',
        'rera', 'builder', 'flat', 'apartment', 'common area',
        'development agreement', 'power of attorney', 'agreement to sell',
        'conveyance', 'transfer', 'assignment', 'novation'
    }

    def __init__(self, records: List[Dict]):
        self.records = records
        self.vectorizer = None
        self.tfidf_matrix = None
        self.document_texts = []
        self.document_metadata = []
        self._prepare_documents()
        self._build_index()

    def _preprocess_text(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        words = [w for w in text.split() if w not in self.STOPWORDS and len(w) > 2]
        return ' '.join(words)

    def _extract_legal_principles(self, text: str) -> List[str]:
        principles = []
        patterns = [
            r'(?:held|observed|ruled|decided|determined|found|concluded)\s+that\s+([^.;]{50,200})',
            r'(?:principle|doctrine|rule|law)\s+(?:of|is|states)\s+([^.;]{50,200})',
            r'(?:section|article)\s+\d+[^.;]{30,150}'
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text.lower())
            principles.extend(matches[:3])
        return principles[:5]

    def _prepare_documents(self):
        for record in self.records:
            texts = []
            if record.get('title'):
                texts.append(record['title'] * 2)
            if record.get('keywords'):
                keyword_text = ' '.join(record['keywords'] * 5)
                texts.append(keyword_text)
            if record.get('summary'):
                texts.append(record['summary'])
            if record.get('rag', {}).get('retrieval_text'):
                texts.append(record['rag']['retrieval_text'])
            if record.get('section_headings'):
                texts.append(' '.join(record['section_headings']) * 2)
            if record.get('document_type'):
                texts.append(record['document_type'] * 3)

            combined_text = ' '.join(texts)
            processed_text = self._preprocess_text(combined_text)
            self.document_texts.append(processed_text)

            raw_text = record.get('rag', {}).get('retrieval_text', '')
            legal_principles = self._extract_legal_principles(raw_text)
            sections = record.get('section_headings', [])[:5]
            preview = raw_text[:500] + "..." if len(raw_text) > 500 else raw_text

            meta = record.get('metadata', {})
            locations = record.get('locations', {}) if isinstance(record.get('locations'), dict) else {}
            self.document_metadata.append({
                'id': record['id'],
                'title': record.get('title', ''),
                'document_type': record.get('document_type', ''),
                'keywords': record.get('keywords', []),
                'summary': record.get('summary', ''),
                'section_headings': record.get('section_headings', []),
                'stats': record.get('stats', {}),
                'court': meta.get('court', '') if isinstance(meta, dict) else '',
                'judgment_date': meta.get('date_of_judgment', '') if isinstance(meta, dict) else '',
                'citation': meta.get('citation', '') if isinstance(meta, dict) else '',
                'parties': meta.get('parties', []) if isinstance(meta, dict) else [],
                'verdict': meta.get('verdict_order', '') if isinstance(meta, dict) else '',
                'legal_principles': legal_principles,
                'relevant_sections': sections,
                'full_text_preview': preview,
                'raw_text': raw_text,
                'relative_path': locations.get('relative_path', ''),
                'source_file': locations.get('source_file', '')
            })

    def _build_index(self):
        self.vectorizer = TfidfVectorizer(
            max_features=15000,
            ngram_range=(1, 3),
            min_df=2,
            max_df=0.90,
            sublinear_tf=True
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.document_texts)

    def query(self, user_scenario: str, top_k: int = 5, 
              doc_type_filter: Optional[str] = None) -> List[RetrievedDocument]:
        processed_query = self._preprocess_text(user_scenario)
        query_words = set(processed_query.split())
        legal_matches = query_words.intersection(self.LEGAL_KEYWORDS)
        if legal_matches:
            boost_text = ' '.join(list(legal_matches) * 3)
            processed_query = processed_query + ' ' + boost_text

        query_vector = self.vectorizer.transform([processed_query])
        similarities = cosine_similarity(query_vector, self.tfidf_matrix).flatten()

        if doc_type_filter:
            for i, meta in enumerate(self.document_metadata):
                if meta['document_type'] != doc_type_filter:
                    similarities[i] = -1

        top_indices = np.argsort(similarities)[::-1]
        top_indices = [idx for idx in top_indices if similarities[idx] > 0][:top_k]

        results = []
        for rank, idx in enumerate(top_indices, 1):
            meta = self.document_metadata[idx]
            doc = RetrievedDocument(
                rank=rank,
                id=meta['id'],
                title=meta['title'],
                document_type=meta['document_type'],
                similarity_score=float(similarities[idx]),
                keywords=meta['keywords'],
                summary=meta['summary'],
                court=meta['court'],
                judgment_date=meta['judgment_date'],
                citation=meta['citation'],
                parties=meta['parties'],
                verdict=meta['verdict'],
                legal_principles=meta['legal_principles'],
                relevant_sections=meta['relevant_sections'],
                full_text_preview=meta['full_text_preview'],
                stats=meta['stats'],
                relative_path=meta.get('relative_path', ''),
                source_file=meta.get('source_file', '')
            )
            results.append(doc)
        return results

    def get_confidence_level(self, score: float) -> str:
        if score >= 0.20:
            return "HIGH"
        elif score >= 0.12:
            return "MEDIUM"
        elif score >= 0.08:
            return "MODERATE"
        else:
            return "LOW"

    def format_results(self, results: List[RetrievedDocument]) -> str:
        lines = []
        lines.append("="*80)
        lines.append("LEGAL PROPERTY RIGHTS - RAG RETRIEVAL RESULTS")
        lines.append("="*80)
        lines.append(f"Total Documents in Database: {len(self.records)}")
        lines.append(f"Document Types: {Counter(r['document_type'] for r in self.records)}")
        lines.append("")

        for doc in results:
            confidence = self.get_confidence_level(doc.similarity_score)
            lines.append("─"*80)
            lines.append(f"RANK #{doc.rank}  |  Relevance: {doc.similarity_score:.4f}  |  Confidence: {confidence}")
            lines.append("─"*80)
            lines.append(f"📄 Title: {doc.title}")
            lines.append(f"🏷️  Type: {doc.document_type.upper()}")

            if doc.court:
                lines.append(f"⚖️  Court: {doc.court}")
            if doc.judgment_date:
                lines.append(f"📅 Date: {doc.judgment_date}")
            if doc.citation:
                lines.append(f"📚 Citation: {doc.citation[:100]}")

            lines.append(f"🔑 Keywords: {', '.join(doc.keywords[:6])}")

            if doc.legal_principles:
                lines.append(f"⚖️  Key Legal Principles:")
                for principle in doc.legal_principles[:3]:
                    lines.append(f"   • {principle[:120]}...")

            if doc.relevant_sections:
                lines.append(f"📋 Relevant Sections:")
                for section in doc.relevant_sections[:3]:
                    lines.append(f"   • {section[:100]}")

            lines.append(f"📝 Summary: {doc.summary[:200]}...")
            lines.append("")

        lines.append("="*80)
        lines.append("END OF RESULTS")
        lines.append("="*80)
        return "\n".join(lines)


def main():
    """Demo usage of the Legal Property RAG Pipeline"""

    # Load manifest
    with open('property_rights_rag_manifest.json', 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    records = manifest['records']

    # Initialize RAG
    print("Initializing Legal Property RAG Pipeline...")
    rag = LegalPropertyRAG(records)
    print(f"Loaded {len(records)} documents")

    # Example user scenario
    scenario = input("Describe your property rights scenario: ").strip()
    if not scenario:
        scenario = (
            "I bought a small plot of land two years ago after checking the sale deed "
            "and paying the full amount. Recently, when I started construction, my neighbor "
            "claimed that part of the land actually belongs to him according to older boundary "
            "records. Now both of us have different documents showing different measurements."
        )

    # Query
    results = rag.query(scenario, top_k=5)

    # Display
    print(rag.format_results(results))

    # Get JSON for integration
    json_results = [doc.to_dict() for doc in results]
    with open('retrieval_results.json', 'w', encoding='utf-8') as f:
        json.dump(json_results, f, indent=2, ensure_ascii=False)
    print("\nResults saved to retrieval_results.json")

if __name__ == "__main__":
    main()
