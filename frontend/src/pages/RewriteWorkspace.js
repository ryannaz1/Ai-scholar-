import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import {
  BookOpen, ArrowLeft, Loader2, Sparkles, Save, ScanText,
  AlertTriangle, Lightbulb, Wand2, Eye, EyeOff
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// ---------- Heuristic AI-tell detector (client-side, real-time) ----------
const AI_CLICHES = [
  'delve into', 'navigate the complexities', 'in today\'s world', 'in conclusion',
  'it is important to note', "it's important to note", 'it is worth noting',
  'a tapestry of', 'intricate', 'multifaceted', 'plays a pivotal role',
  'in the realm of', 'a testament to', 'underscores the importance',
  'furthermore,', 'moreover,', 'additionally,', 'on the other hand,',
  'it is crucial', 'it is essential', 'shed light on', 'paramount importance',
  'unprecedented', 'paradigm shift', 'leveraging', 'foster',
];
const HEDGES = [
  'arguably', 'somewhat', 'perhaps', 'generally', 'typically',
  'in some cases', 'to some extent', 'it could be argued',
];

function findOccurrences(text, needle) {
  const out = [];
  if (!needle) return out;
  const lower = text.toLowerCase();
  const n = needle.toLowerCase();
  let idx = 0;
  while ((idx = lower.indexOf(n, idx)) !== -1) {
    out.push({ start: idx, end: idx + n.length });
    idx += n.length;
  }
  return out;
}

function detectHeuristics(text) {
  if (!text) return { issues: [], stats: {} };
  const issues = [];

  for (const phrase of AI_CLICHES) {
    for (const { start, end } of findOccurrences(text, phrase)) {
      issues.push({
        phrase: text.slice(start, end),
        type: 'cliche',
        why: 'Commonly overused AI cliché — sounds generic.',
        suggestion: 'Replace with a specific, concrete claim or example.',
        start, end, source: 'heuristic',
      });
    }
  }
  for (const phrase of HEDGES) {
    for (const { start, end } of findOccurrences(text, phrase)) {
      issues.push({
        phrase: text.slice(start, end),
        type: 'hedge',
        why: 'Hedging language weakens the argument.',
        suggestion: 'Commit to a clear position or cite evidence.',
        start, end, source: 'heuristic',
      });
    }
  }

  // Em-dash density
  const emDashes = (text.match(/—/g) || []).length;
  // Sentence stats
  const sentences = text.match(/[^.!?\n]+[.!?]/g) || [];
  const lengths = sentences.map(s => s.trim().split(/\s+/).length);
  const avg = lengths.length ? lengths.reduce((a, b) => a + b, 0) / lengths.length : 0;
  const variance = lengths.length
    ? lengths.reduce((sum, l) => sum + Math.pow(l - avg, 2), 0) / lengths.length
    : 0;
  const stdDev = Math.sqrt(variance);
  const uniformity = avg > 0 ? stdDev / avg : 1; // lower = more uniform = more AI-ish

  // Compute a rough AI-likelihood (0-100). NOT a guarantee — just a guide.
  const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
  const clicheRate = issues.filter(i => i.type === 'cliche').length / Math.max(1, wordCount / 100);
  const emDashRate = emDashes / Math.max(1, wordCount / 100);
  let aiScore = 0;
  aiScore += Math.min(40, clicheRate * 20);
  aiScore += Math.min(20, emDashRate * 10);
  if (uniformity < 0.35 && lengths.length >= 4) aiScore += 25;
  if (avg > 22) aiScore += 10;
  aiScore = Math.min(100, Math.round(aiScore));

  return {
    issues,
    stats: {
      words: wordCount,
      sentences: lengths.length,
      avgSentenceLen: Math.round(avg * 10) / 10,
      emDashes,
      uniformity: Math.round(uniformity * 100) / 100,
      heuristicAiScore: aiScore,
    },
  };
}

const typeColor = {
  cliche: 'bg-rose-100 text-rose-700 border-rose-200',
  hedge: 'bg-amber-100 text-amber-700 border-amber-200',
  uniform: 'bg-violet-100 text-violet-700 border-violet-200',
  abstract: 'bg-sky-100 text-sky-700 border-sky-200',
  em_dash: 'bg-fuchsia-100 text-fuchsia-700 border-fuchsia-200',
  passive: 'bg-teal-100 text-teal-700 border-teal-200',
  other: 'bg-slate-100 text-slate-700 border-slate-200',
};

const RewriteWorkspace = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [assignment, setAssignment] = useState(null);
  const [text, setText] = useState('');
  const [llmIssues, setLlmIssues] = useState([]);
  const [llmSummary, setLlmSummary] = useState('');
  const [llmAiScore, setLlmAiScore] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [autoAnalyze, setAutoAnalyze] = useState(true);
  const [showHighlights, setShowHighlights] = useState(true);
  const debounceRef = useRef(null);
  const lastAnalyzedRef = useRef('');

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/assignments/${id}`);
        setAssignment(res.data);
        // Seed with the AI draft so student can start rewriting
        setText(res.data.draft || res.data.generated_content || '');
      } catch (e) {
        toast.error('Failed to load assignment');
        navigate('/dashboard');
      }
    })();
  }, [id, navigate]);

  // Heuristic (instant, every render)
  const heuristic = useMemo(() => detectHeuristics(text), [text]);

  // Debounced LLM analysis
  const runLlmAnalyze = useCallback(async (snapshot) => {
    if (!snapshot || snapshot.trim().length < 80) return;
    if (snapshot === lastAnalyzedRef.current) return;
    setAnalyzing(true);
    try {
      const res = await axios.post(`${API}/rewrite-coach/analyze`, { text: snapshot, mode: 'paragraph' });
      lastAnalyzedRef.current = snapshot;
      setLlmIssues(res.data.issues || []);
      setLlmSummary(res.data.summary || '');
      setLlmAiScore(typeof res.data.ai_likelihood === 'number' ? res.data.ai_likelihood : null);
    } catch (e) {
      // Silent fail in auto mode; surface on manual
    } finally {
      setAnalyzing(false);
    }
  }, []);

  useEffect(() => {
    if (!autoAnalyze) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runLlmAnalyze(text), 1800);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  }, [text, autoAnalyze, runLlmAnalyze]);

  const manualAnalyze = async () => {
    if (!text.trim()) {
      toast.error('Nothing to analyze yet');
      return;
    }
    setAnalyzing(true);
    try {
      const res = await axios.post(`${API}/rewrite-coach/analyze`, { text, mode: 'draft' });
      lastAnalyzedRef.current = text;
      setLlmIssues(res.data.issues || []);
      setLlmSummary(res.data.summary || '');
      setLlmAiScore(typeof res.data.ai_likelihood === 'number' ? res.data.ai_likelihood : null);
      toast.success('Deep analysis complete');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Analysis failed');
    } finally {
      setAnalyzing(false);
    }
  };

  // Combine heuristic + LLM issues, dedupe by phrase
  const allIssues = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const i of heuristic.issues) {
      const key = (i.phrase || '').toLowerCase();
      if (!seen.has(key)) { seen.add(key); out.push(i); }
    }
    for (const i of llmIssues) {
      const key = (i.phrase || '').toLowerCase();
      if (!seen.has(key)) { seen.add(key); out.push({ ...i, source: 'llm' }); }
    }
    return out;
  }, [heuristic.issues, llmIssues]);

  // Build highlighted overlay (matches textarea visually-positioned div)
  const overlayHtml = useMemo(() => {
    if (!showHighlights) return null;
    if (!text) return null;
    // Mark all heuristic spans (have start/end). LLM-only have no positions, skip them in overlay.
    const spans = heuristic.issues
      .filter(i => typeof i.start === 'number')
      .sort((a, b) => a.start - b.start);
    if (spans.length === 0) return text;
    const parts = [];
    let cursor = 0;
    spans.forEach((s, idx) => {
      if (s.start < cursor) return;
      parts.push(escapeHtml(text.slice(cursor, s.start)));
      parts.push(
        `<mark data-i="${idx}" style="background: rgba(244,63,94,0.18); border-bottom: 2px dotted rgba(244,63,94,0.6); border-radius: 2px;">${escapeHtml(text.slice(s.start, s.end))}</mark>`
      );
      cursor = s.end;
    });
    parts.push(escapeHtml(text.slice(cursor)));
    return parts.join('');
  }, [text, heuristic.issues, showHighlights]);

  const applySuggestion = (issue) => {
    if (!issue.phrase) return;
    if (!issue.suggestion) return;
    const next = text.replaceAll(issue.phrase, issue.suggestion);
    if (next === text) {
      toast.info('Phrase not found in current text');
      return;
    }
    setText(next);
    toast.success('Suggestion applied');
  };

  const orderAiCheck = async (tier) => {
    if (!text || text.trim().split(/\s+/).filter(Boolean).length < 50) {
      toast.error('Write at least 50 words before ordering an AI check.');
      return;
    }
    try {
      const res = await axios.post(`${API}/ai-check/order`, {
        assignment_id: id,
        tier,
        text_to_check: text,
        origin_url: window.location.origin,
      });
      window.location.href = res.data.url;
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to create order');
    }
  };

  if (!assignment) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  const blendedScore = llmAiScore != null
    ? Math.round((llmAiScore + heuristic.stats.heuristicAiScore) / 2)
    : heuristic.stats.heuristicAiScore;

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-border/40 bg-white sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 md:px-6 py-3 flex items-center gap-3">
          <Link to={`/assignment/${id}`} className="text-muted-foreground hover:text-foreground" data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <BookOpen className="w-5 h-5 text-primary flex-shrink-0" strokeWidth={1.5} />
            <span className="text-base font-semibold text-primary truncate" style={{ fontFamily: 'Fraunces, serif' }}>
              Rewrite Workspace
            </span>
            <span className="hidden md:inline text-sm text-muted-foreground truncate"> · {assignment.title}</span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowHighlights(s => !s)}
              data-testid="toggle-highlights-btn"
            >
              {showHighlights ? <EyeOff className="w-4 h-4 mr-1" /> : <Eye className="w-4 h-4 mr-1" />}
              {showHighlights ? 'Hide flags' : 'Show flags'}
            </Button>
            <Button size="sm" onClick={manualAnalyze} disabled={analyzing} data-testid="deep-analyze-btn">
              {analyzing ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <ScanText className="w-4 h-4 mr-1" />}
              Deep analyze
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 md:px-6 py-6 grid lg:grid-cols-5 gap-6">
        {/* Editor */}
        <div className="lg:col-span-3">
          <Card className="bg-white border border-border/40 rounded-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="text-base" style={{ fontFamily: 'Fraunces, serif' }}>Your Rewrite</CardTitle>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span data-testid="word-count">{heuristic.stats.words || 0} words</span>
                  <span>·</span>
                  <span data-testid="sentence-count">{heuristic.stats.sentences || 0} sentences</span>
                  <span>·</span>
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoAnalyze}
                      onChange={(e) => setAutoAnalyze(e.target.checked)}
                      data-testid="auto-analyze-toggle"
                    />
                    Auto-analyze
                  </label>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="relative">
                {showHighlights && overlayHtml !== null && (
                  <div
                    aria-hidden="true"
                    className="absolute inset-0 p-3 text-[15px] leading-7 whitespace-pre-wrap break-words pointer-events-none text-transparent overflow-hidden"
                    style={{ fontFamily: 'Georgia, serif' }}
                    // eslint-disable-next-line react/no-danger
                    dangerouslySetInnerHTML={{ __html: overlayHtml + '<br/>' }}
                  />
                )}
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  className="relative w-full min-h-[560px] p-3 text-[15px] leading-7 bg-transparent border border-border rounded-sm outline-none focus:ring-2 focus:ring-primary/30 resize-y"
                  style={{ fontFamily: 'Georgia, serif' }}
                  placeholder="Start rewriting the AI draft in your own voice…"
                  data-testid="rewrite-textarea"
                  spellCheck="true"
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right rail */}
        <div className="lg:col-span-2 space-y-4">
          {/* Score */}
          <Card className="bg-white border border-border/40 rounded-sm" data-testid="score-card">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">AI-likelihood (guide)</p>
                  <p className="text-3xl font-bold font-mono mt-1" data-testid="ai-score">
                    {blendedScore}<span className="text-base text-muted-foreground">/100</span>
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-1">Not a guarantee — use a real detector before submitting.</p>
                </div>
                <div className={`w-16 h-16 rounded-full flex items-center justify-center ${
                  blendedScore < 30 ? 'bg-green-100 text-green-700' : blendedScore < 60 ? 'bg-amber-100 text-amber-700' : 'bg-rose-100 text-rose-700'
                }`}>
                  {blendedScore < 30 ? <Sparkles className="w-7 h-7" /> : <AlertTriangle className="w-7 h-7" />}
                </div>
              </div>
              {llmSummary && (
                <div className="mt-3 pt-3 border-t border-border/40 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">Coach: </span>{llmSummary}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Issues */}
          <Card className="bg-white border border-border/40 rounded-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base" style={{ fontFamily: 'Fraunces, serif' }}>AI Tells</CardTitle>
                <Badge variant="outline" data-testid="issue-count">{allIssues.length}</Badge>
              </div>
            </CardHeader>
            <CardContent>
              {allIssues.length === 0 ? (
                <p className="text-sm text-muted-foreground py-6 text-center">
                  ✨ No obvious AI tells detected. Keep writing.
                </p>
              ) : (
                <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
                  {allIssues.map((issue, idx) => (
                    <div
                      key={`${issue.phrase}-${idx}`}
                      className="border border-border/60 rounded-sm p-3 text-sm hover:bg-secondary/30 transition-colors"
                      data-testid={`issue-${idx}`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <Badge className={`text-[10px] uppercase tracking-wide ${typeColor[issue.type] || typeColor.other}`}>
                          {issue.type || 'other'}
                        </Badge>
                        {issue.source === 'llm' && (
                          <span className="text-[10px] text-violet-600 flex items-center gap-1">
                            <Wand2 className="w-3 h-3" /> AI coach
                          </span>
                        )}
                      </div>
                      <p className="font-mono text-[13px] text-rose-700 mb-1">"{issue.phrase}"</p>
                      <p className="text-xs text-muted-foreground mb-2">{issue.why}</p>
                      {issue.suggestion && (
                        <div className="flex items-start gap-2 bg-emerald-50 border border-emerald-100 rounded-sm p-2">
                          <Lightbulb className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0 mt-0.5" />
                          <p className="text-[13px] text-emerald-900 flex-1">{issue.suggestion}</p>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-[11px]"
                            onClick={() => applySuggestion(issue)}
                            data-testid={`apply-${idx}`}
                          >
                            Apply
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Order AI check */}
          <Card className="bg-white border border-border/40 rounded-sm" data-testid="ai-check-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-base" style={{ fontFamily: 'Fraunces, serif' }}>Order an AI Check</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Submit your <span className="font-medium text-foreground">final rewrite</span> for a real, manual AI-detection report. We'll email you the result within 24 h.
              </p>
              <div className="grid grid-cols-2 gap-2">
                <Button
                  variant="outline"
                  className="rounded-sm"
                  onClick={() => orderAiCheck('originality')}
                  data-testid="order-originality-btn"
                >
                  Originality.ai
                  <span className="ml-auto font-mono">$10</span>
                </Button>
                <Button
                  className="rounded-sm bg-primary text-primary-foreground hover:bg-primary/90"
                  onClick={() => orderAiCheck('turnitin')}
                  data-testid="order-turnitin-btn"
                >
                  Turnitin
                  <span className="ml-auto font-mono">$15</span>
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Reports are produced manually by our reviewer using a verified account, then emailed to you.
              </p>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
};

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export default RewriteWorkspace;
