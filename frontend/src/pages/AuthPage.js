import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { BookOpen, Mail, Lock, User, ArrowRight, Loader2, Gift } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';

const AuthPage = ({ mode = 'login' }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { login, register } = useAuth();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: ''
  });
  const [referralCode, setReferralCode] = useState('');

  const isLogin = mode === 'login';
  const from = location.state?.from?.pathname || '/dashboard';

  useEffect(() => {
    const ref = searchParams.get('ref');
    if (ref) {
      setReferralCode(ref);
      // Persist so it survives login→register toggle
      try { sessionStorage.setItem('pending_ref', ref); } catch (e) {}
    } else {
      try {
        const stored = sessionStorage.getItem('pending_ref');
        if (stored) setReferralCode(stored);
      } catch (e) {}
    }
  }, [searchParams]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (isLogin) {
        await login(formData.email, formData.password);
        toast.success('Welcome back!');
      } else {
        if (!formData.name.trim()) {
          toast.error('Please enter your name');
          setLoading(false);
          return;
        }
        await register(formData.email, formData.password, formData.name, referralCode || null);
        toast.success(referralCode ? 'Account created — $5 credit will be added on your first paid order!' : 'Account created successfully!');
        try { sessionStorage.removeItem('pending_ref'); } catch (e) {}
      }
      navigate(from, { replace: true });
    } catch (error) {
      const message = error.response?.data?.detail || 'Authentication failed';
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      {/* Header */}
      <header className="p-6">
        <Link to="/" className="flex items-center gap-2 w-fit" data-testid="auth-logo">
          <BookOpen className="w-7 h-7 text-primary" strokeWidth={1.5} />
          <span className="text-xl font-semibold text-primary" style={{ fontFamily: 'Fraunces, serif' }}>AIScholar</span>
        </Link>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center px-6 pb-12">
        <Card className="w-full max-w-md border border-border/40 shadow-sm rounded-sm" data-testid="auth-card">
          <CardHeader className="text-center pb-2">
            <CardTitle className="text-2xl font-semibold" style={{ fontFamily: 'Fraunces, serif' }}>
              {isLogin ? 'Welcome Back' : 'Create Account'}
            </CardTitle>
            <CardDescription className="text-muted-foreground">
              {isLogin ? 'Sign in to continue your writing journey' : 'Start improving your academic writing today'}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              {!isLogin && (
                <div className="space-y-2">
                  <Label htmlFor="name" className="text-sm font-medium">Full Name</Label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="name"
                      name="name"
                      type="text"
                      placeholder="John Doe"
                      value={formData.name}
                      onChange={handleChange}
                      className="pl-10 rounded-sm"
                      data-testid="name-input"
                      required={!isLogin}
                    />
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email" className="text-sm font-medium">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    id="email"
                    name="email"
                    type="email"
                    placeholder="you@university.edu"
                    value={formData.email}
                    onChange={handleChange}
                    className="pl-10 rounded-sm"
                    data-testid="email-input"
                    required
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="password" className="text-sm font-medium">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    id="password"
                    name="password"
                    type="password"
                    placeholder="••••••••"
                    value={formData.password}
                    onChange={handleChange}
                    className="pl-10 rounded-sm"
                    data-testid="password-input"
                    required
                    minLength={6}
                  />
                </div>
              </div>

              {!isLogin && referralCode && (
                <div className="flex items-center gap-2 p-3 rounded-sm bg-accent/10 border border-accent/30" data-testid="referral-banner">
                  <Gift className="w-4 h-4 text-accent flex-shrink-0" />
                  <p className="text-xs text-foreground">
                    You were invited by a friend — <b>$5 credit</b> will be added when you complete your first paid order.
                  </p>
                </div>
              )}

              <Button
                type="submit"
                className="w-full bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm py-5"
                disabled={loading}
                data-testid="auth-submit-btn"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                ) : null}
                {isLogin ? 'Sign In' : 'Create Account'}
                {!loading && <ArrowRight className="ml-2 w-4 h-4" />}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-muted-foreground">
                {isLogin ? "Don't have an account?" : "Already have an account?"}
                {' '}
                <Link
                  to={isLogin ? '/register' : '/login'}
                  className="text-primary hover:underline font-medium"
                  data-testid="auth-toggle-link"
                >
                  {isLogin ? 'Sign up' : 'Sign in'}
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

export default AuthPage;
