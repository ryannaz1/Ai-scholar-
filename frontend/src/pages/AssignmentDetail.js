import React, { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { 
  BookOpen, ArrowLeft, CreditCard, Loader2, 
  FileText, Download, Sparkles, CheckCircle, Clock,
  Copy, AlertCircle
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const AssignmentDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [assignment, setAssignment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    fetchAssignment();
  }, [id]);

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
        origin_url: window.location.origin
      });
      
      // Redirect to Stripe checkout
      window.location.href = res.data.url;
    } catch (error) {
      const message = error.response?.data?.detail || 'Payment failed';
      toast.error(message);
      setPaying(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await axios.post(`${API}/assignments/${id}/generate`);
      toast.success('Content generated successfully!');
      await fetchAssignment();
    } catch (error) {
      const message = error.response?.data?.detail || 'Generation failed';
      toast.error(message);
    } finally {
      setGenerating(false);
    }
  };

  const copyContent = () => {
    if (assignment?.generated_content) {
      navigator.clipboard.writeText(assignment.generated_content);
      toast.success('Content copied to clipboard!');
    }
  };

  const downloadContent = () => {
    if (assignment?.generated_content) {
      const blob = new Blob([assignment.generated_content], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${assignment.title.replace(/[^a-z0-9]/gi, '_')}.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('Content downloaded!');
    }
  };

  const getStatusBadge = (status) => {
    const statusConfig = {
      draft: { label: 'Awaiting Payment', className: 'bg-yellow-100 text-yellow-800', icon: <Clock className="w-3 h-3" /> },
      paid: { label: 'Ready to Generate', className: 'bg-blue-100 text-blue-800', icon: <Sparkles className="w-3 h-3" /> },
      completed: { label: 'Completed', className: 'bg-green-100 text-green-800', icon: <CheckCircle className="w-3 h-3" /> }
    };
    const config = statusConfig[status] || statusConfig.draft;
    return (
      <Badge className={`${config.className} flex items-center gap-1`}>
        {config.icon}
        {config.label}
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

  if (!assignment) {
    return null;
  }

  return (
    <div className="min-h-screen bg-paper">
      {/* Header */}
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
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl md:text-3xl font-semibold text-foreground" style={{ fontFamily: 'Fraunces, serif' }}>
                {assignment.title}
              </h1>
              {getStatusBadge(assignment.status)}
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
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Requirements Card */}
            <Card className="bg-white border border-border/40 rounded-sm" data-testid="requirements-card">
              <CardHeader>
                <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>Requirements</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground whitespace-pre-wrap">{assignment.requirements}</p>
                {assignment.additional_notes && (
                  <div className="mt-4 pt-4 border-t border-border/40">
                    <p className="text-sm font-medium mb-2">Additional Notes</p>
                    <p className="text-sm text-muted-foreground">{assignment.additional_notes}</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Generated Content */}
            {assignment.generated_content && (
              <Card className="bg-white border border-border/40 rounded-sm" data-testid="content-card">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>Generated Content</CardTitle>
                    <div className="flex items-center gap-2">
                      <Button 
                        variant="outline" 
                        size="sm" 
                        onClick={copyContent}
                        className="rounded-sm"
                        data-testid="copy-btn"
                      >
                        <Copy className="w-4 h-4 mr-1" /> Copy
                      </Button>
                      <Button 
                        variant="outline" 
                        size="sm" 
                        onClick={downloadContent}
                        className="rounded-sm"
                        data-testid="download-btn"
                      >
                        <Download className="w-4 h-4 mr-1" /> Download
                      </Button>
                    </div>
                  </div>
                  <CardDescription>
                    {assignment.generated_content.split(/\s+/).length.toLocaleString()} words generated
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="writing-area prose prose-sm max-w-none" data-testid="generated-content">
                    {assignment.generated_content.split('\n').map((paragraph, index) => (
                      <p key={index} className="mb-4">{paragraph}</p>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Sidebar Actions */}
          <div className="lg:col-span-1">
            <Card className="bg-white border border-border/40 rounded-sm sticky top-8" data-testid="action-sidebar">
              <CardHeader>
                <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>Actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Draft Status - Payment needed */}
                {assignment.status === 'draft' && (
                  <>
                    <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-sm">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-medium text-yellow-800">Payment Required</p>
                          <p className="text-sm text-yellow-700 mt-1">
                            Complete payment to start generating your content.
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

                {/* Paid Status - Ready to generate */}
                {assignment.status === 'paid' && (
                  <>
                    <div className="p-4 bg-blue-50 border border-blue-200 rounded-sm">
                      <div className="flex items-start gap-2">
                        <Sparkles className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-medium text-blue-800">Ready to Generate</p>
                          <p className="text-sm text-blue-700 mt-1">
                            Click below to generate your academic content with AI.
                          </p>
                        </div>
                      </div>
                    </div>
                    <Button
                      className="w-full bg-accent text-accent-foreground hover:bg-accent/90 rounded-sm py-5"
                      onClick={handleGenerate}
                      disabled={generating}
                      data-testid="generate-btn"
                    >
                      {generating ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin mr-2" />
                          Generating...
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-4 h-4 mr-2" />
                          Generate Content
                        </>
                      )}
                    </Button>
                  </>
                )}

                {/* Completed Status */}
                {assignment.status === 'completed' && (
                  <div className="p-4 bg-green-50 border border-green-200 rounded-sm">
                    <div className="flex items-start gap-2">
                      <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="font-medium text-green-800">Content Ready</p>
                        <p className="text-sm text-green-700 mt-1">
                          Your content has been generated. Use it as a learning reference!
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Info */}
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
