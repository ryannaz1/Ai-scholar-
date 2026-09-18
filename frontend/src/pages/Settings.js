import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { BookOpen, ArrowLeft, Mail, Save, Loader2, CheckCircle2, Info, Send } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Settings = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [senderEmail, setSenderEmail] = useState('');
  const [fallback, setFallback] = useState('');
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [isAdmin, setIsAdmin] = useState(null);
  const [testTo, setTestTo] = useState('');
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const admin = await axios.get(`${API}/auth/me-admin`);
        setIsAdmin(!!admin.data.is_admin);
        if (!admin.data.is_admin) {
          setLoading(false);
          return;
        }
        const res = await axios.get(`${API}/settings/resend`);
        setSenderEmail(res.data.sender_email || '');
        setFallback(res.data.fallback_sender_email || '');
        setKeyConfigured(!!res.data.api_key_configured);
      } catch (e) {
        toast.error('Failed to load settings');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/settings/resend`, { sender_email: senderEmail.trim() });
      toast.success('Settings saved');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleTestSend = async () => {
    const to = testTo.trim();
    if (!to) return toast.error('Enter an email to send the test to');
    setTesting(true);
    try {
      const res = await axios.post(`${API}/settings/resend/test`, { to_email: to });
      toast.success(`Test email sent — from ${res.data.from}. Check ${to}'s inbox.`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Test send failed');
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (isAdmin === false) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center p-6">
        <Card className="max-w-md w-full border border-border/40 rounded-sm">
          <CardContent className="p-8 text-center">
            <h2 className="text-xl font-semibold mb-2" style={{ fontFamily: 'Fraunces, serif' }}>Admin only</h2>
            <p className="text-muted-foreground mb-6">This settings page is for the app owner.</p>
            <Link to="/dashboard">
              <Button className="rounded-sm">Back to dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-border/40 bg-white">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center gap-4">
          <Link to="/dashboard" className="text-muted-foreground hover:text-foreground" data-testid="settings-back-btn">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-primary" strokeWidth={1.5} />
            <span className="text-lg font-semibold text-primary" style={{ fontFamily: 'Fraunces, serif' }}>AIScholar</span>
          </div>
          <span className="ml-auto text-sm text-muted-foreground">Settings</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10 space-y-8">
        <div>
          <h1 className="text-3xl md:text-4xl font-semibold mb-2" style={{ fontFamily: 'Fraunces, serif' }}>Settings</h1>
          <p className="text-muted-foreground">Admin-only configuration for transactional email.</p>
        </div>

        <Card className="bg-white border border-border/40 rounded-sm" data-testid="resend-settings-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg" style={{ fontFamily: 'Fraunces, serif' }}>
              <Mail className="w-5 h-5 text-primary" />
              Resend sender email
            </CardTitle>
            <CardDescription>
              Paste an address on a domain you've verified in Resend (e.g. <code>orders@yourdomain.com</code>).
              Once saved, order confirmations and report emails will send from this address.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="flex items-start gap-3 p-3 rounded-sm bg-blue-50 border border-blue-100">
              <Info className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
              <div className="text-xs text-blue-900 leading-relaxed">
                <p className="mb-1"><b>API key status:</b> {keyConfigured ? <span className="text-green-700 inline-flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Configured</span> : <span className="text-red-700">Missing — set RESEND_API_KEY in backend .env</span>}</p>
                <p><b>Fallback sender (used if empty):</b> <code>{fallback}</code></p>
                <p className="mt-1">Verify your domain at{' '}
                  <a href="https://resend.com/domains" target="_blank" rel="noreferrer" className="text-primary underline">resend.com/domains</a>{' '}
                  before pasting an address here — otherwise emails to students will silently fail.
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="sender-email">Sender email address</Label>
              <Input
                id="sender-email"
                type="email"
                placeholder="orders@yourdomain.com"
                value={senderEmail}
                onChange={(e) => setSenderEmail(e.target.value)}
                className="rounded-sm"
                data-testid="resend-sender-input"
              />
              <p className="text-xs text-muted-foreground">Leave empty to use the Resend fallback (test mode — only sends to your registered address).</p>
            </div>

            <Button
              onClick={handleSave}
              disabled={saving}
              className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm"
              data-testid="save-resend-btn"
            >
              {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
              Save settings
            </Button>

            <div className="pt-5 border-t border-border/40 space-y-3">
              <Label htmlFor="test-to">Send a test email</Label>
              <div className="flex flex-col sm:flex-row gap-2">
                <Input
                  id="test-to"
                  type="email"
                  placeholder="you@yourdomain.com"
                  value={testTo}
                  onChange={(e) => setTestTo(e.target.value)}
                  className="rounded-sm flex-1"
                  data-testid="test-email-input"
                />
                <Button
                  onClick={handleTestSend}
                  disabled={testing || !keyConfigured}
                  variant="outline"
                  className="rounded-sm"
                  data-testid="send-test-btn"
                >
                  {testing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
                  Send test
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                In Resend test mode you can only send to <code>{fallback === 'onboarding@resend.dev' ? 'ryannazha@gmail.com' : fallback}</code>. After verifying your domain, this will work for any address.
              </p>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

export default Settings;
