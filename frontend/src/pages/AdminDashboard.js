import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  BookOpen, ArrowLeft, Loader2, Upload, CheckCircle, Clock,
  FileText, Mail, Hourglass, ShieldCheck, AlertTriangle
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Textarea } from '../components/ui/textarea';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const statusMeta = {
  pending_payment: { label: 'Awaiting payment', cls: 'bg-yellow-100 text-yellow-800', Icon: Clock },
  paid: { label: 'Queued for review', cls: 'bg-blue-100 text-blue-800', Icon: Hourglass },
  in_progress: { label: 'In progress', cls: 'bg-purple-100 text-purple-800', Icon: Loader2 },
  completed: { label: 'Completed', cls: 'bg-green-100 text-green-800', Icon: CheckCircle },
};

const AdminDashboard = () => {
  const navigate = useNavigate();
  const [authChecking, setAuthChecking] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeOrder, setActiveOrder] = useState(null);
  const [notes, setNotes] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/auth/me-admin`);
        setIsAdmin(!!res.data.is_admin);
        if (res.data.is_admin) await loadOrders();
      } catch (e) {
        setIsAdmin(false);
      } finally {
        setAuthChecking(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadOrders = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/admin/ai-check/orders`);
      setOrders(res.data || []);
    } catch (e) {
      toast.error('Failed to load orders');
    } finally {
      setLoading(false);
    }
  };

  const markInProgress = async (orderId) => {
    try {
      await axios.post(`${API}/admin/ai-check/orders/${orderId}/mark-in-progress`);
      toast.success('Marked in progress');
      loadOrders();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed');
    }
  };

  const submitReport = async (file) => {
    if (!activeOrder || !file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append('report', file);
    fd.append('notes', notes || '');
    try {
      await axios.post(
        `${API}/admin/ai-check/orders/${activeOrder.id}/complete`,
        fd,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      toast.success('Report uploaded — student emailed');
      setActiveOrder(null);
      setNotes('');
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadOrders();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  if (authChecking) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-paper flex flex-col items-center justify-center p-6">
        <AlertTriangle className="w-12 h-12 text-amber-500 mb-4" />
        <h1 className="text-2xl font-semibold mb-2" style={{ fontFamily: 'Fraunces, serif' }}>Admin only</h1>
        <p className="text-muted-foreground mb-6">This page is restricted to the Scholar reviewer.</p>
        <Button onClick={() => navigate('/dashboard')} className="rounded-sm">Back to dashboard</Button>
      </div>
    );
  }

  const counts = orders.reduce((acc, o) => {
    acc[o.status] = (acc[o.status] || 0) + 1;
    return acc;
  }, {});
  const pendingOrders = orders.filter(o => ['paid', 'in_progress'].includes(o.status));
  const completedOrders = orders.filter(o => o.status === 'completed');

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-border/40 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center gap-3">
          <Link to="/dashboard" className="text-muted-foreground hover:text-foreground" data-testid="back-btn">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex items-center gap-2 flex-1">
            <ShieldCheck className="w-5 h-5 text-primary" strokeWidth={1.5} />
            <span className="text-lg font-semibold text-primary" style={{ fontFamily: 'Fraunces, serif' }}>
              Reviewer Dashboard
            </span>
          </div>
          <Button variant="outline" size="sm" onClick={loadOrders} data-testid="refresh-btn">
            Refresh
          </Button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-6 space-y-6">
        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Awaiting payment', value: counts.pending_payment || 0 },
            { label: 'Queued', value: counts.paid || 0 },
            { label: 'In progress', value: counts.in_progress || 0 },
            { label: 'Completed', value: counts.completed || 0 },
          ].map(s => (
            <Card key={s.label} className="bg-white border border-border/40 rounded-sm" data-testid={`stat-${s.label}`}>
              <CardContent className="p-4">
                <p className="text-2xl font-bold font-mono">{s.value}</p>
                <p className="text-xs text-muted-foreground">{s.label}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Pending */}
        <Card className="bg-white border border-border/40 rounded-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-base" style={{ fontFamily: 'Fraunces, serif' }}>
              Pending Reviews ({pendingOrders.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? (
              <div className="p-8 text-center text-muted-foreground"><Loader2 className="w-5 h-5 animate-spin inline" /></div>
            ) : pendingOrders.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground text-sm">No pending orders. ✨</div>
            ) : (
              <div className="divide-y divide-border/40">
                {pendingOrders.map(o => {
                  const meta = statusMeta[o.status] || statusMeta.paid;
                  const Icon = meta.Icon;
                  return (
                    <div key={o.id} className="p-4 flex flex-col md:flex-row md:items-center gap-3" data-testid={`order-${o.id}`}>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <Badge className={`${meta.cls} flex items-center gap-1`}>
                            <Icon className="w-3 h-3" /> {meta.label}
                          </Badge>
                          <Badge variant="outline">{o.tier === 'turnitin' ? 'Turnitin · $15' : 'Originality · $10'}</Badge>
                          <span className="text-xs text-muted-foreground font-mono">{o.id.slice(0, 8)}</span>
                        </div>
                        <p className="font-medium text-sm truncate">{o.assignment_title}</p>
                        <p className="text-xs text-muted-foreground">
                          {o.student_name} · <a className="underline" href={`mailto:${o.student_email}`}>{o.student_email}</a> · {o.word_count} words
                        </p>
                      </div>
                      <div className="flex gap-2 flex-shrink-0">
                        {o.status === 'paid' && (
                          <Button variant="outline" size="sm" onClick={() => markInProgress(o.id)} data-testid={`progress-${o.id}`}>
                            Mark in progress
                          </Button>
                        )}
                        <Button size="sm" onClick={() => { setActiveOrder(o); setNotes(''); }} data-testid={`complete-${o.id}`}>
                          <Upload className="w-4 h-4 mr-1" /> Upload report
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Completed */}
        <Card className="bg-white border border-border/40 rounded-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-base" style={{ fontFamily: 'Fraunces, serif' }}>
              Recently Completed ({completedOrders.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {completedOrders.length === 0 ? (
              <div className="p-6 text-center text-muted-foreground text-sm">Nothing completed yet.</div>
            ) : (
              <div className="divide-y divide-border/40">
                {completedOrders.slice(0, 20).map(o => (
                  <div key={o.id} className="p-3 text-sm flex items-center justify-between">
                    <div className="min-w-0">
                      <p className="font-medium truncate">{o.assignment_title}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {o.student_email} · {o.tier} · completed {o.completed_at?.slice(0, 10)}
                      </p>
                    </div>
                    <Badge className="bg-green-100 text-green-800">Done</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </main>

      {/* Upload modal */}
      {activeOrder && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50" onClick={() => !uploading && setActiveOrder(null)}>
          <div
            className="bg-white rounded-sm shadow-xl max-w-lg w-full p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
            data-testid="upload-modal"
          >
            <div>
              <h3 className="text-lg font-semibold" style={{ fontFamily: 'Fraunces, serif' }}>Upload report</h3>
              <p className="text-xs text-muted-foreground mt-1">
                For <b>{activeOrder.assignment_title}</b> · {activeOrder.student_email}
              </p>
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Report file (PDF preferred)</label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.doc,.txt"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) submitReport(f);
                }}
                disabled={uploading}
                className="block w-full text-sm"
                data-testid="report-file-input"
              />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Notes for the student (optional)</label>
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. AI score 4%, mostly clean. Two paragraphs flagged — see highlighted sections in PDF."
                className="rounded-sm min-h-[80px]"
                disabled={uploading}
                data-testid="notes-input"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="ghost"
                onClick={() => setActiveOrder(null)}
                disabled={uploading}
                data-testid="cancel-btn"
              >
                Cancel
              </Button>
              <Button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                data-testid="choose-file-btn"
              >
                {uploading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Uploading…</> : <><Upload className="w-4 h-4 mr-2" /> Choose file & send</>}
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground flex items-center gap-1">
              <Mail className="w-3 h-3" /> Student is auto-emailed the report when you upload.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDashboard;
