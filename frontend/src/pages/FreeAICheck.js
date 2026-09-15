import React, { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  BookOpen, ArrowLeft, Sparkles, Loader2, AlertTriangle,
  ShieldCheck, Lightbulb, ScanText, ChevronRight
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const FREE_CHAR_LIMIT = 4000;

const typeColor = {
  cliche: 'bg-rose-100 text-rose-700',
  hedge: 'bg-amber-100 text-amber-700',
  uniform: 'bg-violet-100 text-violet-700',
  abstract: 'bg-sky-100 text-sky-700',
  em_dash: 'bg-fuchsia-100 text-fuchsia-700',
  passive: 'bg-teal-100 text-teal-700',
  other: 'bg-slate-100 text-slate-700',
};

const FreeAICheck = () => {
  const [text, setText] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const wordCount = useMemo(() => text.trim() ? text.trim().split(/\s+/).length : 0, [text]);
  const charCount = text.length;
  const overLimit = charCount > FREE_CHAR_LIMIT;

  const runCheck = async () => {
    if (!text.trim()) {
      toast.error('Paste some text first');
      return;
    }
    if (overLimit) {
      toast.error(`Free tier limit is ${FREE_CHAR_LIMIT} characters (~${Math.floor(FREE_CHAR_LIMIT/6)} words).`);
      return;
    }
    setLoading(true);
    try {
      const res = await axios.post(`${API}/free-ai-check`, { text });
      setResult(res.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Check failed');
    } finally {
      setLoading(false);
    }
  };

  const score = result?.ai_likelihood;
  const verdict = score == null ? null
    : score < 30 ? { label: 'Likely human', cls: 'text-green-700 bg-green-100', Icon: Sparkles }
    : score < 60 ? { label: 'Some AI signals', cls: 'text-amber-700 bg-amber-100', Icon: AlertTriangle }
    : { label: 'Likely AI-generated', cls: 'text-rose-700 bg-rose-100', Icon: AlertTriangle };

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-border/40 bg-white">
        <div className="max-w-5xl mx-auto px-4 md:px-6 py-4 flex items-center gap-3">
          <Link to="/" className="text-muted-foreground hover:text-foreground" data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <Link to="/" className="flex items-center gap-2 flex-1">
            <BookOpen className="w-6 h-6 text-primary" strokeWidth={1.5} />
            <span className="text-lg font-semibold text-primary" style={{ fontFamily: 'Fraunces, serif' }}>AIScholar</span>
          </Link>
          <Link to="/register">
            <Button size="sm" variant="outline" data-testid="signup-btn">Sign up — unlimited</Button>
          </Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 md:px-6 py-8 lg:py-12">
        <div className="text-center mb-8">
          <Badge className="bg-primary/10 text-primary mb-3">Free AI Detector · No signup required</Badge>
          <h1 className="text-3xl md:text-5xl font-semibold mb-3" style={{ fontFamily: 'Fraunces, serif' }}>
            Free <span className="text-accent">AI Content Detector</span>
          </h1>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            Paste your writing and find out if a teacher or AI checker might flag it. Powered by GPT-5.2.
            5 free checks per day · up to {Math.floor(FREE_CHAR_LIMIT/6)} words each.
          </p>
        </div>

        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <Card className="bg-white border border-border/40 rounded-sm">
              <CardContent className="p-4">
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Paste up to ~700 words of your writing here…"
                  className="w-full min-h-[280px] p-3 text-[15px] leading-7 border border-border rounded-sm outline-none focus:ring-2 focus:ring-primary/30 resize-y"
                  style={{ fontFamily: 'Georgia, serif' }}
                  data-testid="check-textarea"
                />
                <div className="flex items-center justify-between mt-3 text-xs text-muted-foreground">
                  <span data-testid="char-counter">
                    {charCount.toLocaleString()} / {FREE_CHAR_LIMIT.toLocaleString()} chars · {wordCount} words
                  </span>
                  <Button onClick={runCheck} disabled={loading || overLimit || !text.trim()} data-testid="run-check-btn">
                    {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ScanText className="w-4 h-4 mr-2" />}
                    Run AI check
                  </Button>
                </div>
                {overLimit && (
                  <p className="text-xs text-rose-600 mt-2">
                    Over the free limit. <Link to="/register" className="underline">Create a free account</Link> for unlimited checks + larger documents.
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Upsell */}
            <Card className="bg-secondary/40 border border-border/40 rounded-sm mt-4">
              <CardContent className="p-4 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="font-medium text-sm" style={{ fontFamily: 'Fraunces, serif' }}>Need more than the free tier?</p>
                  <p className="text-xs text-muted-foreground">Premium reports from Originality.ai ($10) or Turnitin ($15) — produced manually by our reviewer with a PDF report.</p>
                </div>
                <Link to="/register">
                  <Button variant="default" size="sm" className="rounded-sm flex-shrink-0">
                    Sign up <ChevronRight className="w-4 h-4 ml-1" />
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </div>

          {/* Result */}
          <div>
            {result ? (
              <Card className="bg-white border border-border/40 rounded-sm" data-testid="result-card">
                <CardContent className="p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs uppercase tracking-wider text-muted-foreground">AI likelihood</span>
                    {verdict && (
                      <Badge className={`${verdict.cls} flex items-center gap-1`}>
                        <verdict.Icon className="w-3 h-3" /> {verdict.label}
                      </Badge>
                    )}
                  </div>
                  <div className="text-center">
                    <p className="text-5xl font-bold font-mono" data-testid="score">
                      {score ?? '—'}<span className="text-xl text-muted-foreground">/100</span>
                    </p>
                  </div>
                  {result.summary && (
                    <div className="border-t border-border/40 pt-3">
                      <p className="text-xs text-muted-foreground">{result.summary}</p>
                    </div>
                  )}
                  <div className="border-t border-border/40 pt-3">
                    <p className="text-xs font-semibold mb-2">Top flagged phrases</p>
                    {result.issues?.length ? (
                      <div className="space-y-2 max-h-[280px] overflow-y-auto">
                        {result.issues.map((i, idx) => (
                          <div key={idx} className="text-xs border border-border/40 rounded-sm p-2" data-testid={`issue-${idx}`}>
                            <Badge className={`${typeColor[i.type] || typeColor.other} text-[9px] uppercase`}>{i.type || 'other'}</Badge>
                            <p className="font-mono text-rose-700 mt-1 text-[12px]">"{i.phrase}"</p>
                            {i.suggestion && (
                              <p className="text-emerald-700 mt-1 flex gap-1">
                                <Lightbulb className="w-3 h-3 mt-0.5 flex-shrink-0" />
                                {i.suggestion}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground italic">No obvious flags — looks human ✨</p>
                    )}
                  </div>
                  {typeof result.remaining_today === 'number' && (
                    <p className="text-[11px] text-muted-foreground text-center pt-2 border-t border-border/40">
                      {result.remaining_today} free check(s) remaining today
                    </p>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card className="bg-white border border-border/40 rounded-sm">
                <CardContent className="p-5 text-center">
                  <ShieldCheck className="w-10 h-10 text-primary/70 mx-auto mb-3" />
                  <p className="text-sm font-medium" style={{ fontFamily: 'Fraunces, serif' }}>Your AI score appears here</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    We use the same coach AIScholar customers get — minus the regenerate & rewrite tools.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>

        {/* SEO content block */}
        <section className="mt-16 max-w-3xl mx-auto prose prose-sm text-muted-foreground">
          <h2 className="text-xl font-semibold text-foreground" style={{ fontFamily: 'Fraunces, serif' }}>
            About this free AI essay checker
          </h2>
          <p>
            AIScholar's free AI content detector is built for students who want to quickly find out whether their essay,
            lab report, literature review, or Master's thesis chapter reads as AI-generated to their teacher's detection tools.
            Paste up to 700 words and get an instant AI-likelihood score plus a list of "AI tells" — clichés, hedge phrases,
            uniform sentence rhythm, and other patterns that AI detectors look for.
          </p>
          <p>
            <strong>Why use AIScholar's checker?</strong> Unlike single-purpose AI detectors, AIScholar pairs the score
            with concrete, actionable rewrite suggestions powered by GPT-5.2. You don't just see a number — you see
            exactly what to change. Sign up free for unlimited checks, larger documents, and a side-by-side Rewrite
            Workspace that flags AI-isms as you edit in real time.
          </p>
          <p>
            <strong>Looking for a paid detector report?</strong> AIScholar reviewers can run your text through Originality.ai ($10)
            or Turnitin ($15) using verified accounts, then email you the official PDF report within 24 hours.
          </p>
        </section>
      </main>
    </div>
  );
};

export default FreeAICheck;
