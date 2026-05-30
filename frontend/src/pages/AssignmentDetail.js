import React, { useState, useEffect, useRef } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import {
  BookOpen, ArrowLeft, CreditCard, Loader2,
  Download, Sparkles, CheckCircle, Clock,
  Copy, AlertCircle, ListTree, FileText, Lightbulb, RefreshCw
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
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
  const [assignment, setAssignment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [activeTab, setActiveTab] = useState('outline');
  const pollTimerRef = useRef(null);

  useEffect(() => {
    fetchAssignment();
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

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
            <span className="text-lg font-semibold text-primary" style={{ fontFamily: 'Fraunces, serif' }}>Scholar</span>
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

            {/* Generating state */}
            {isGenerating && (
              <Card className="bg-white border border-border/40 rounded-sm" data-testid="generating-card">
                <CardContent className="p-8 text-center">
                  <Loader2 className="w-10 h-10 text-primary mx-auto mb-4 animate-spin" />
                  <h3 className="text-lg font-semibold mb-1" style={{ fontFamily: 'Fraunces, serif' }}>
                    Crafting your learning materials…
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    This usually takes 20–60 seconds. We'll refresh automatically.
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
                      return (
                        <TabsContent key={key} value={key} data-testid={`tab-content-${key}`}>
                          <div className="flex items-center justify-between mb-3">
                            <p className="text-sm text-muted-foreground">{meta.description}</p>
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
                          {text ? (
                            <div className="writing-area prose prose-sm max-w-none whitespace-pre-wrap" data-testid={`section-${key}`}>
                              {text}
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
                    <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-sm">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-medium text-yellow-800">Payment Required</p>
                          <p className="text-sm text-yellow-700 mt-1">
                            Complete payment and AI generation will begin automatically.
                          </p>
                        </div>
                      </div>
                    </div>
                    <Button
                      className="w-full bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm py-5"
                      onClick={handlePayment}
                      disabled={paying}
                      data-testid="pay-btn"
                    >
                      {paying ? (
                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                      ) : (
                        <CreditCard className="w-4 h-4 mr-2" />
                      )}
                      Pay ${assignment.final_price}
                    </Button>
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
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
};

export default AssignmentDetail;
