import React, { useState, useEffect, useRef } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { BookOpen, CheckCircle, Loader2, AlertCircle, ArrowRight, Sparkles } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import confetti from 'canvas-confetti';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const PaymentSuccess = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const sessionId = searchParams.get('session_id');
  const [status, setStatus] = useState('checking'); // checking, success, error
  const [assignmentId, setAssignmentId] = useState(null);
  const confettiFiredRef = useRef(false);

  const fireConfetti = () => {
    if (confettiFiredRef.current) return;
    confettiFiredRef.current = true;
    const colors = ['#1a2842', '#c9a961', '#f5f1e8', '#22c55e'];
    const duration = 2500;
    const end = Date.now() + duration;
    (function frame() {
      confetti({ particleCount: 4, angle: 60, spread: 55, origin: { x: 0 }, colors });
      confetti({ particleCount: 4, angle: 120, spread: 55, origin: { x: 1 }, colors });
      if (Date.now() < end) requestAnimationFrame(frame);
    })();
    confetti({ particleCount: 140, spread: 100, origin: { y: 0.55 }, colors, scalar: 1.15 });
  };

  useEffect(() => {
    if (sessionId) {
      pollPaymentStatus(sessionId);
    } else {
      setStatus('error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const pollPaymentStatus = async (sid, attempts = 0) => {
    const maxAttempts = 8;
    const pollInterval = 2000;

    if (attempts >= maxAttempts) {
      setStatus('error');
      toast.error('Payment verification timed out. Please check your dashboard.');
      return;
    }

    try {
      const res = await axios.get(`${API}/payments/status/${sid}`);

      if (res.data.payment_status === 'paid') {
        setStatus('success');
        fireConfetti();
        if (res.data.assignment_id) {
          setAssignmentId(res.data.assignment_id);
          // Give user 4s to enjoy the confetti + confirmation message before redirecting
          setTimeout(() => {
            navigate(`/assignment/${res.data.assignment_id}?paid=1`);
          }, 4000);
        }
        toast.success('Payment successful! AI is drafting your assignment now.');
        return;
      }

      // Continue polling
      setTimeout(() => pollPaymentStatus(sid, attempts + 1), pollInterval);
    } catch (error) {
      console.error('Error checking payment status:', error);
      setTimeout(() => pollPaymentStatus(sid, attempts + 1), pollInterval);
    }
  };

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      {/* Header */}
      <header className="p-6">
        <Link to="/" className="flex items-center gap-2 w-fit" data-testid="success-logo">
          <BookOpen className="w-7 h-7 text-primary" strokeWidth={1.5} />
          <span className="text-xl font-semibold text-primary" style={{ fontFamily: 'Fraunces, serif' }}>AIScholar</span>
        </Link>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center px-6 pb-12">
        <Card className="w-full max-w-md border border-border/40 shadow-sm rounded-sm" data-testid="payment-result-card">
          <CardContent className="p-8 text-center">
            {status === 'checking' && (
              <>
                <Loader2 className="w-16 h-16 text-primary mx-auto mb-6 animate-spin" />
                <h1 className="text-2xl font-semibold mb-2" style={{ fontFamily: 'Fraunces, serif' }}>
                  Verifying Payment...
                </h1>
                <p className="text-muted-foreground">
                  Please wait while we confirm your payment.
                </p>
              </>
            )}

            {status === 'success' && (
              <>
                <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6 animate-in zoom-in duration-500">
                  <CheckCircle className="w-10 h-10 text-green-600" />
                </div>
                <h1 className="text-2xl font-semibold mb-2" style={{ fontFamily: 'Fraunces, serif' }}>
                  Payment Successful!
                </h1>
                <div className="flex items-center justify-center gap-2 mb-3 text-primary">
                  <Sparkles className="w-4 h-4" />
                  <p className="text-sm font-medium">AI is now making your assignment</p>
                  <Sparkles className="w-4 h-4" />
                </div>
                <p className="text-muted-foreground mb-6 text-sm">
                  It'll be ready in a bit — please be patient, quality writing takes a moment.
                  We're taking you to your assignment page…
                </p>
                {assignmentId ? (
                  <Link to={`/assignment/${assignmentId}?paid=1`}>
                    <Button
                      className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm px-8"
                      data-testid="view-assignment-btn"
                    >
                      Open my assignment <ArrowRight className="ml-2 w-4 h-4" />
                    </Button>
                  </Link>
                ) : (
                  <Link to="/dashboard">
                    <Button
                      className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm px-8"
                      data-testid="go-dashboard-btn"
                    >
                      Go to Dashboard <ArrowRight className="ml-2 w-4 h-4" />
                    </Button>
                  </Link>
                )}
              </>
            )}

            {status === 'error' && (
              <>
                <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-6">
                  <AlertCircle className="w-10 h-10 text-red-600" />
                </div>
                <h1 className="text-2xl font-semibold mb-2" style={{ fontFamily: 'Fraunces, serif' }}>
                  Verification Failed
                </h1>
                <p className="text-muted-foreground mb-6">
                  We couldn't verify your payment. Please check your dashboard or contact support.
                </p>
                <Link to="/dashboard">
                  <Button 
                    className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm px-8"
                    data-testid="error-dashboard-btn"
                  >
                    Go to Dashboard
                  </Button>
                </Link>
              </>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

export default PaymentSuccess;
