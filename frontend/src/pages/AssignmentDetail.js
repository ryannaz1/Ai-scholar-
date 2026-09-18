import React, { useState, useEffect, useRef } from 'react';
import { Link, useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  BookOpen, ArrowLeft, CreditCard, Loader2,
  Download, Sparkles, CheckCircle, Clock,
  Copy, AlertCircle, ListTree, FileText, Lightbulb, RefreshCw, Wand2, ShieldCheck, Hourglass, Download as DownloadIcon, Copy as DuplicateIcon
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import confetti from 'canvas-confetti';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const SECTION_META = {
  outline: { label: 'Outline', icon: ListTree, description: 'Structural blueprint of the assignment' },
  draft: { label: 'Draft', icon: FileText, description: 'Reference draft at requested word count' },
  writing_tips: { label: 'Writing Tips', icon: Lightbulb, description: 'Personalized guidance to make it your own' },
};

const AssignmentDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [assignment, setAssignment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [activeTab, setActiveTab] = useState('outline');
  const [aiCheckOrders, setAiCheckOrders] = useState([]);
  const [regenerating, setRegenerating] = useState(false);
  const [references, setReferences] = useState(null);
  const [refsLoading, setRefsLoading] = useState(false);
  const [paymentAttempts, setPaymentAttempts] = useState(0);
  const [justPaid, setJustPaid] = useState(false);
  const pollTimerRef = useRef(null);
  const confettiFiredRef = useRef(false);

  const fireConfetti = () => {
    if (confettiFiredRef.current) return;
    confettiFiredRef.current = true;
    const duration = 2500;
    const end = Date.now() + duration;
    const colors = ['#1a2842', '#c9a961', '#f5f1e8', '#22c55e'];
    (function frame() {
      confetti({ particleCount: 4, angle: 60, spread: 55, origin: { x: 0 }, colors });
      confetti({ particleCount: 4, angle: 120, spread: 55, origin: { x: 1 }, colors });
      if (Date.now() < end) requestAnimationFrame(frame);
    })();
    confetti({ particleCount: 120, spread: 90, origin: { y: 0.6 }, colors, scalar: 1.1 });
  };

  useEffect(() => {
    fetchAssignment();
    fetchAiCheckOrders();
    fetchPaymentAttempts();
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Detect landing here fresh from Stripe checkout success
  useEffect(() => {
    if (searchParams.get('paid') === '1') {
      setJustPaid(true);
      fireConfetti();
      toast.success('Payment received — AI is drafting now.');
      searchParams.delete('paid');
      setSearchParams(searchParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchPaymentAttempts = async () => {
    try {
      const res = await axios.get(`${API}/payments/attempts/${id}`);
      setPaymentAttempts(res.data.attempts || 0);
    } catch (e) {/* silent */}
  };

  // If returning from Stripe with ai_check_session, confirm payment & refresh
  useEffect(() => {
    const sess = searchParams.get('ai_check_session');
    const regenSess = searchParams.get('regen_session');
    if (sess) {
      (async () => {
        try {
          const res = await axios.get(`${API}/ai-check/status/${sess}`);
          if (res.data.status === 'paid') {
            toast.success('AI check order received — we\'ll email you the report within 24 h.');
          }
        } catch (e) {/* silent */}
        finally {
          searchParams.delete('ai_check_session');
          setSearchParams(searchParams, { replace: true });
          fetchAiCheckOrders();
        }
      })();
    }
    if (regenSess) {
      (async () => {
        try {
          const res = await axios.get(`${API}/assignments/${id}/regen-status/${regenSess}`);
          if (res.data.status === 'regenerating') {
            toast.success(`Payment received — regenerating ${res.data.section}…`);
            setRegenerating(true);
          }
        } catch (e) {/* silent */}
        finally {
          searchParams.delete('regen_session');
          setSearchParams(searchParams, { replace: true });
          fetchAssignment();
        }
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const handleRegenerate = async (section) => {
    setRegenerating(true);
    try {
      const res = await axios.post(`${API}/assignments/${id}/regenerate/${section}`, {
        origin_url: window.location.origin,
      });
      if (res.data.status === 'payment_required' && res.data.checkout_url) {
        toast.info('Redirecting to checkout — $5 for this regeneration.');
        window.location.href = res.data.checkout_url;
        return;
      }
      if (res.data.status === 'regenerating') {
        toast.success(`Regenerating ${section.replace('_', ' ')}… ${res.data.remaining_free} free regen(s) remaining after this.`);
        // Trigger poll loop
        setTimeout(fetchAssignment, 3000);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Regenerate failed');
    } finally {
      // Will be cleared when generation_status transitions back to completed
      setTimeout(() => setRegenerating(false), 1500);
    }
  };

  const fetchAiCheckOrders = async () => {
    try {
      const res = await axios.get(`${API}/ai-check/orders/${id}`);
      setAiCheckOrders(res.data || []);
    } catch (e) {
      // silent
    }
  };

  const fetchReferences = async () => {
    setRefsLoading(true);
    try {
      const res = await axios.get(`${API}/assignments/${id}/suggested-references?limit=8`);
      setReferences(res.data.references || []);
    } catch (e) {
      toast.error('Could not load references');
      setReferences([]);
    } finally {
      setRefsLoading(false);
    }
  };

  const downloadReport = async (orderId, filename) => {
    try {
      const res = await axios.get(`${API}/ai-check/orders/${orderId}/report`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || `ai_check_report_${orderId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      toast.error('Could not download report');
    }
  };

  const [previewingPrev, setPreviewingPrev] = useState(null); // 'outline' | 'draft' | 'writing_tips'

  const formatTimeAgo = (iso) => {
    if (!iso) return null;
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diffSec = Math.floor((now - then) / 1000);
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  };

  // Auto-poll while generation is in progress
  useEffect(() => {
    if (!assignment) return;
    const gs = assignment.generation_status;
    if (gs === 'generating' || (assignment.status === 'paid' && gs === 'pending')) {
      pollTimerRef.current = setTimeout(fetchAssignment, 4000);
    }
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment?.generation_status, assignment?.status]);

  const fetchAssignment = async () => {
    try {
      const res = await axios.get(`${API}/assignments/${id}`);
      setAssignment(res.data);
    } catch (error) {
      toast.error('Failed to load assignment');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  };

  const handlePayment = async () => {
    setPaying(true);
    try {
      const res = await axios.post(`${API}/payments/checkout`, {
        assignment_id: id,
        origin_url: window.location.origin,
      });
      window.location.href = res.data.url;
    } catch (error) {
      const message = error.response?.data?.detail || 'Payment failed';
      toast.error(message);
      setPaying(false);
    }
  };

  const handleGenerate = async () => {
    try {
      await axios.post(`${API}/assignments/${id}/generate`);
      toast.info('Generation started — this may take up to a minute.');
      fetchAssignment();
    } catch (error) {
      const message = error.response?.data?.detail || 'Generation failed to start';
      toast.error(message);
    }
  };

  const [duplicating, setDuplicating] = useState(false);
  const handleDuplicate = async () => {
    setDuplicating(true);
    try {
      const res = await axios.post(`${API}/assignments/${id}/duplicate`);
      toast.success('Assignment duplicated');
      navigate(`/assignment/${res.data.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Duplicate failed');
    } finally {
      setDuplicating(false);
    }
  };

  const copySection = (text, label) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard`);
  };

  const downloadFull = () => {
    if (!assignment?.generated_content) return;
    const blob = new Blob([assignment.generated_content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${assignment.title.replace(/[^a-z0-9]/gi, '_')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success('Downloaded full document');
  };

  const getStatusBadge = (status, genStatus) => {
    if (genStatus === 'generating') {
      return (
        <Badge className="bg-purple-100 text-purple-800 flex items-center gap-1" data-testid="status-badge">
          <Loader2 className="w-3 h-3 animate-spin" /> Generating
        </Badge>
      );
    }
    if (genStatus === 'failed') {
      return (
        <Badge className="bg-red-100 text-red-800 flex items-center gap-1" data-testid="status-badge">
          <AlertCircle className="w-3 h-3" /> Generation Failed
        </Badge>
      );
    }
    const map = {
      draft: { label: 'Awaiting Payment', className: 'bg-yellow-100 text-yellow-800', Icon: Clock },
      paid: { label: 'Ready to Generate', className: 'bg-blue-100 text-blue-800', Icon: Sparkles },
      completed: { label: 'Completed', className: 'bg-green-100 text-green-800', Icon: CheckCircle },
    };
    const c = map[status] || map.draft;
    const Icon = c.Icon;
    return (
      <Badge className={`${c.className} flex items-center gap-1`} data-testid="status-badge">
        <Icon className="w-3 h-3" /> {c.label}
      </Badge>
    );
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!assignment) return null;

  const isGenerating = assignment.generation_status === 'generating';
  const isFailed = assignment.generation_status === 'failed';
  const hasContent = assignment.outline || assignment.draft || assignment.writing_tips;

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-border/40 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center gap-4">
          <Link to="/dashboard" className="text-muted-foreground hover:text-foreground" data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-primary" strokeWidth={1.5} />
            <span className="text-lg font-semibold text-primary" style={{ fontFamily: 'Fraunces, serif' }}>AIScholar</span>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 mb-8">
          <div>
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <h1 className="text-2xl md:text-3xl font-semibold text-foreground" style={{ fontFamily: 'Fraunces, serif' }}>
                {assignment.title}
              </h1>
              {getStatusBadge(assignment.status, assignment.generation_status)}
            </div>
            <p className="text-muted-foreground">
              {assignment.subject} • {assignment.word_count.toLocaleString()} words
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Total</p>
            <p className="font-mono text-2xl font-bold text-primary" data-testid="assignment-price">
              ${assignment.final_price}
            </p>
            {assignment.discount_applied && (
              <span className="text-xs text-accent">10% discount applied</span>
            )}
          </div>
        </div>

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Main */}
          <div className="lg:col-span-2 space-y-6">
            <Card className="bg-white border border-border/40 rounded-sm" data-testid="requirements-card">
              <CardHeader>
                <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>Requirements</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground whitespace-pre-wrap">{assignment.requirements}</p>
                {assignment.additional_notes && (
                  <div className="mt-4 pt-4 border-t border-border/40">
                    <p className="text-sm font-medium mb-2">Additional Notes</p>
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">{assignment.additional_notes}</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Suggested Public References */}
            <Card className="bg-white border border-border/40 rounded-sm" data-testid="refs-card">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <CardTitle className="text-lg flex items-center gap-2" style={{ fontFamily: 'Fraunces, serif' }}>
                    <BookOpen className="w-5 h-5 text-primary" /> Public References
                  </CardTitle>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={fetchReferences}
                    disabled={refsLoading}
                    data-testid="load-refs-btn"
                  >
                    {refsLoading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1" />}
                    {references === null ? 'Find references' : 'Refresh'}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {references === null ? (
                  <p className="px-6 py-4 text-sm text-muted-foreground">
                    Tap "Find references" to pull publicly accessible scholarly papers from CrossRef matching your topic.
                  </p>
                ) : references.length === 0 ? (
                  <p className="px-6 py-4 text-sm text-muted-foreground">No matching references found. Try rewording your title/subject.</p>
                ) : (
                  <div className="divide-y divide-border/40">
                    {references.map((r, i) => (
                      <div key={r.doi || i} className="p-4 text-sm" data-testid={`ref-${i}`}>
                        <a
                          href={r.url || (r.doi ? `https://doi.org/${r.doi}` : '#')}
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-primary hover:underline block leading-snug"
                        >
                          {r.title}
                        </a>
                        <p className="text-xs text-muted-foreground mt-1">
                          {r.authors}{r.year ? ` · ${r.year}` : ''}{r.venue ? ` · ${r.venue}` : ''}
                        </p>
                        {r.abstract_excerpt && (
                          <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{r.abstract_excerpt}…</p>
                        )}
                        {r.doi && (
                          <p className="text-[11px] text-muted-foreground mt-1 font-mono">DOI: {r.doi}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Just-paid confirmation banner */}
            {justPaid && (
              <Card className="bg-white border-2 border-green-300 rounded-sm shadow-sm" data-testid="just-paid-card">
                <CardContent className="p-6 text-center">
                  <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-3">
                    <CheckCircle className="w-8 h-8 text-green-600" />
                  </div>
                  <h3 className="text-xl font-semibold mb-2" style={{ fontFamily: 'Fraunces, serif' }}>
                    Payment received — thank you!
                  </h3>
                  <p className="text-sm text-muted-foreground max-w-md mx-auto">
                    Your assignment is now being crafted by our AI writing assistant.
                    It'll be ready in a bit — please be patient, quality writing takes a moment.
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-3">
                    A confirmation email is on its way. You can safely close this page and come back later.
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Generating state */}
            {isGenerating && (
              <Card className="bg-white border border-border/40 rounded-sm" data-testid="generating-card">
                <CardContent className="p-8 text-center">
                  <Loader2 className="w-10 h-10 text-primary mx-auto mb-4 animate-spin" />
                  <h3 className="text-lg font-semibold mb-1" style={{ fontFamily: 'Fraunces, serif' }}>
                    Your assignment is being made by AI…
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {assignment.word_count >= 3000
                      ? `Long assignment (~${assignment.word_count.toLocaleString()} words) — this can take 2–4 minutes. Please be patient, we refresh automatically.`
                      : 'This usually takes 20–60 seconds. Please be patient — we refresh automatically.'}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-3">
                    Safe to leave this page — your draft will be waiting when you come back.
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Failed state */}
            {isFailed && (
              <Card className="bg-white border border-red-200 rounded-sm" data-testid="failed-card">
                <CardContent className="p-6">
                  <div className="flex items-start gap-3 mb-3">
                    <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="font-medium text-red-800">Generation failed</p>
                      <p className="text-sm text-red-700 mt-1 break-words">
                        {assignment.generation_error || 'Something went wrong. Please retry.'}
                      </p>
                    </div>
                  </div>
                  <Button onClick={handleGenerate} variant="outline" className="rounded-sm" data-testid="retry-btn">
                    <RefreshCw className="w-4 h-4 mr-2" /> Retry generation
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* Tabbed content */}
            {hasContent && !isGenerating && (
              <Card className="bg-white border border-border/40 rounded-sm" data-testid="content-card">
                <CardHeader>
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>
                      Your Learning Materials
                    </CardTitle>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={downloadFull}
                      className="rounded-sm"
                      data-testid="download-btn"
                    >
                      <Download className="w-4 h-4 mr-1" /> Download all
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <TabsList className="grid grid-cols-3 w-full mb-4" data-testid="content-tabs">
                      {Object.entries(SECTION_META).map(([key, meta]) => {
                        const Icon = meta.icon;
                        return (
                          <TabsTrigger key={key} value={key} data-testid={`tab-${key}`}>
                            <Icon className="w-4 h-4 mr-2" />
                            {meta.label}
                          </TabsTrigger>
                        );
                      })}
                    </TabsList>

                    {Object.entries(SECTION_META).map(([key, meta]) => {
                      const text = assignment[key] || '';
                      const regensUsed = assignment[`${key}_regens`] || 0;
                      const remainingFree = Math.max(0, 2 - regensUsed);
                      const regenAt = assignment[`${key}_regenerated_at`];
                      const previousText = assignment[`${key}_previous`] || '';
                      const showingPrev = previewingPrev === key;
                      return (
                        <TabsContent key={key} value={key} data-testid={`tab-content-${key}`}>
                          <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
                            <div className="min-w-0 flex-1">
                              <p className="text-sm text-muted-foreground">{meta.description}</p>
                              {regenAt && (
                                <p className="text-[11px] text-muted-foreground mt-0.5" data-testid={`regen-meta-${key}`}>
                                  Last regenerated {formatTimeAgo(regenAt)} · regen #{regensUsed}
                                  {previousText && (
                                    <>
                                      {' · '}
                                      <button
                                        type="button"
                                        onClick={() => setPreviewingPrev(showingPrev ? null : key)}
                                        className="underline text-primary hover:text-primary/80"
                                        data-testid={`toggle-prev-${key}`}
                                      >
                                        {showingPrev ? 'Hide previous version' : 'View previous version'}
                                      </button>
                                    </>
                                  )}
                                </p>
                              )}
                            </div>
                            <div className="flex items-center gap-1">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleRegenerate(key)}
                                disabled={regenerating || isGenerating}
                                data-testid={`regen-${key}-btn`}
                                title={remainingFree > 0 ? `${remainingFree} free regen(s) left` : 'Next regen costs $5'}
                              >
                                {regenerating ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1" />}
                                {remainingFree > 0 ? `Regenerate (${remainingFree} free)` : 'Regenerate ($5)'}
                              </Button>
                              {text && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => copySection(text, meta.label)}
                                  data-testid={`copy-${key}-btn`}
                                >
                                  <Copy className="w-4 h-4 mr-1" /> Copy
                                </Button>
                              )}
                            </div>
                          </div>
                          {showingPrev && previousText && (
                            <div className="mb-4 border-l-4 border-amber-300 bg-amber-50/50 p-3 rounded-sm" data-testid={`prev-${key}`}>
                              <p className="text-xs uppercase tracking-wide text-amber-700 mb-2 font-semibold">Previous version (before last regen)</p>
                              <div className="prose prose-sm max-w-none opacity-90">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{previousText}</ReactMarkdown>
                              </div>
                            </div>
                          )}
                          {text ? (
                            <div className="writing-area prose prose-sm max-w-none" data-testid={`section-${key}`}>
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
                            </div>
                          ) : (
                            <p className="text-sm text-muted-foreground italic">No {meta.label.toLowerCase()} available.</p>
                          )}
                        </TabsContent>
                      );
                    })}
                  </Tabs>
                </CardContent>
              </Card>
            )}

            {/* AI Check Orders */}
            {aiCheckOrders.length > 0 && (
              <Card className="bg-white border border-border/40 rounded-sm" data-testid="orders-card">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2" style={{ fontFamily: 'Fraunces, serif' }}>
                    <ShieldCheck className="w-5 h-5 text-primary" /> AI Check Orders
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-border/40">
                    {aiCheckOrders.map(o => {
                      const tierLabel = o.tier === 'turnitin' ? 'Turnitin · $15' : 'Originality.ai · $10';
                      const statusBadge = (() => {
                        if (o.status === 'completed') return <Badge className="bg-green-100 text-green-800 flex items-center gap-1"><CheckCircle className="w-3 h-3" /> Report ready</Badge>;
                        if (o.status === 'in_progress') return <Badge className="bg-purple-100 text-purple-800 flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Reviewer working</Badge>;
                        if (o.status === 'paid') return <Badge className="bg-blue-100 text-blue-800 flex items-center gap-1"><Hourglass className="w-3 h-3" /> Queued</Badge>;
                        return <Badge className="bg-yellow-100 text-yellow-800 flex items-center gap-1"><Clock className="w-3 h-3" /> Awaiting payment</Badge>;
                      })();
                      return (
                        <div key={o.order_id || o.id} className="p-4 flex flex-col sm:flex-row sm:items-center gap-3" data-testid={`order-row-${o.id}`}>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                              {statusBadge}
                              <span className="text-xs text-muted-foreground">{tierLabel}</span>
                              <span className="text-xs text-muted-foreground font-mono">{String(o.id).slice(0, 8)}</span>
                            </div>
                            <p className="text-xs text-muted-foreground">
                              {o.word_count} words · ordered {o.created_at?.slice(0, 10)}
                              {o.completed_at && <> · completed {o.completed_at.slice(0, 10)}</>}
                            </p>
                            {o.completion_notes && (
                              <p className="text-xs mt-1 italic text-muted-foreground">"{o.completion_notes}"</p>
                            )}
                          </div>
                          {o.status === 'completed' && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => downloadReport(o.id, o.report_filename)}
                              data-testid={`download-report-${o.id}`}
                            >
                              <DownloadIcon className="w-4 h-4 mr-1" /> Download report
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1">
            <Card className="bg-white border border-border/40 rounded-sm sticky top-8" data-testid="action-sidebar">
              <CardHeader>
                <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>Actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {assignment.status === 'draft' && (
                  <>
                    <div className={`p-4 rounded-sm border ${paymentAttempts > 0 ? 'bg-orange-50 border-orange-200' : 'bg-yellow-50 border-yellow-200'}`}>
                      <div className="flex items-start gap-2">
                        <AlertCircle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${paymentAttempts > 0 ? 'text-orange-600' : 'text-yellow-600'}`} />
                        <div>
                          <p className={`font-medium ${paymentAttempts > 0 ? 'text-orange-800' : 'text-yellow-800'}`}>
                            {paymentAttempts > 0 ? 'Payment not completed' : 'Payment Required'}
                          </p>
                          <p className={`text-sm mt-1 ${paymentAttempts > 0 ? 'text-orange-700' : 'text-yellow-700'}`}>
                            {paymentAttempts > 0
                              ? `You've started ${paymentAttempts} checkout${paymentAttempts > 1 ? 's' : ''} but haven't finished. Tap below to try again — you won't be double-charged.`
                              : 'Complete payment and AI generation will begin automatically.'}
                          </p>
                        </div>
                      </div>
                    </div>
                    <Button
                      className="w-full bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm py-5"
                      onClick={handlePayment}
                      disabled={paying}
                      data-testid={paymentAttempts > 0 ? 'retry-payment-btn' : 'pay-btn'}
                    >
                      {paying ? (
                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                      ) : (
                        <CreditCard className="w-4 h-4 mr-2" />
                      )}
                      {paymentAttempts > 0 ? 'Retry Payment' : 'Pay'} ${assignment.final_price}
                    </Button>
                    {paymentAttempts > 0 && (
                      <p className="text-[11px] text-muted-foreground text-center">
                        Stripe froze last time? Try a different browser or disable ad-blockers on checkout.stripe.com.
                      </p>
                    )}
                  </>
                )}

                {assignment.status === 'paid' && assignment.generation_status !== 'generating' && !hasContent && (
                  <>
                    <div className="p-4 bg-blue-50 border border-blue-200 rounded-sm">
                      <div className="flex items-start gap-2">
                        <Sparkles className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-medium text-blue-800">Ready to Generate</p>
                          <p className="text-sm text-blue-700 mt-1">
                            Start generating your outline, draft, and writing tips.
                          </p>
                        </div>
                      </div>
                    </div>
                    <Button
                      className="w-full bg-accent text-accent-foreground hover:bg-accent/90 rounded-sm py-5"
                      onClick={handleGenerate}
                      data-testid="generate-btn"
                    >
                      <Sparkles className="w-4 h-4 mr-2" />
                      Generate Now
                    </Button>
                  </>
                )}

                {isGenerating && (
                  <div className="p-4 bg-purple-50 border border-purple-200 rounded-sm">
                    <div className="flex items-start gap-2">
                      <Loader2 className="w-5 h-5 text-purple-600 flex-shrink-0 mt-0.5 animate-spin" />
                      <div>
                        <p className="font-medium text-purple-800">Generating…</p>
                        <p className="text-sm text-purple-700 mt-1">
                          Hang tight — this page refreshes automatically.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {assignment.status === 'completed' && hasContent && (
                  <>
                    <div className="p-4 bg-green-50 border border-green-200 rounded-sm">
                      <div className="flex items-start gap-2">
                        <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-medium text-green-800">Materials Ready</p>
                          <p className="text-sm text-green-700 mt-1">
                            Use these as a learning reference — write your final version in your own voice.
                          </p>
                        </div>
                      </div>
                    </div>
                    <Link to={`/assignment/${assignment.id}/workspace`} className="block">
                      <Button
                        className="w-full bg-accent text-accent-foreground hover:bg-accent/90 rounded-sm py-5"
                        data-testid="open-workspace-btn"
                      >
                        <Wand2 className="w-4 h-4 mr-2" />
                        Open Rewrite Workspace
                      </Button>
                    </Link>
                  </>
                )}

                <div className="pt-4 border-t border-border/40 space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Subject</span>
                    <span>{assignment.subject}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Writing Style</span>
                    <span className="capitalize">{assignment.writing_style}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Word Count</span>
                    <span className="font-mono">{assignment.word_count.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Materials</span>
                    <span>{assignment.course_materials?.length || 0} files</span>
                  </div>
                </div>

                <Button
                  variant="outline"
                  className="w-full rounded-sm mt-2"
                  onClick={handleDuplicate}
                  disabled={duplicating}
                  data-testid="duplicate-assignment-btn"
                >
                  {duplicating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <DuplicateIcon className="w-4 h-4 mr-2" />}
                  Duplicate assignment
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
};

export default AssignmentDetail;
