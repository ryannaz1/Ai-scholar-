import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { BookOpen, FileText, DollarSign, Sparkles, ArrowRight, CheckCircle, GraduationCap, Users, Shield } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';

const LandingPage = () => {
  const navigate = useNavigate();
  const [wordCount, setWordCount] = useState(1000);

  const calculatePrice = (words) => {
    const pages = words / 280;
    const basePrice = pages * 7;
    const discount = words >= 10000 ? basePrice * 0.1 : 0;
    return {
      pages: pages.toFixed(1),
      basePrice: basePrice.toFixed(2),
      discount: discount.toFixed(2),
      finalPrice: (basePrice - discount).toFixed(2),
      hasDiscount: words >= 10000
    };
  };

  const pricing = calculatePrice(wordCount);

  const features = [
    {
      icon: <Sparkles className="w-6 h-6" strokeWidth={1.5} />,
      title: "AI-Powered Writing",
      description: "Advanced GPT-5.2 technology creates structured, academic content tailored to your requirements."
    },
    {
      icon: <FileText className="w-6 h-6" strokeWidth={1.5} />,
      title: "Course Material Integration",
      description: "Upload your syllabus and readings to get contextually relevant writing assistance."
    },
    {
      icon: <GraduationCap className="w-6 h-6" strokeWidth={1.5} />,
      title: "Learning-Focused",
      description: "Content designed to help you understand concepts and improve your own writing skills."
    },
    {
      icon: <Shield className="w-6 h-6" strokeWidth={1.5} />,
      title: "Academic Integrity",
      description: "Ethical approach focused on learning templates and writing improvement, not shortcuts."
    }
  ];

  return (
    <div className="min-h-screen bg-paper">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-paper/80 backdrop-blur-sm border-b border-border/40">
        <div className="max-w-7xl mx-auto px-6 md:px-12 lg:px-24">
          <div className="flex items-center justify-between h-16">
            <Link to="/" className="flex items-center gap-2" data-testid="logo">
              <BookOpen className="w-7 h-7 text-primary" strokeWidth={1.5} />
              <span className="text-xl font-semibold text-primary" style={{ fontFamily: 'Fraunces, serif' }}>Scholar</span>
            </Link>
            <div className="flex items-center gap-4">
              <Link to="/login">
                <Button variant="ghost" className="text-primary hover:text-primary/80" data-testid="login-btn">
                  Sign In
                </Button>
              </Link>
              <Link to="/register">
                <Button className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm px-6" data-testid="register-btn">
                  Get Started
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-6 md:px-12 lg:px-24 hero-gradient">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <div className="animate-fade-in-up">
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-semibold text-foreground leading-tight mb-6" style={{ fontFamily: 'Fraunces, serif' }}>
                Your Academic Writing <span className="text-accent">Assistant</span>
              </h1>
              <p className="text-base lg:text-lg text-muted-foreground mb-8 max-w-lg">
                Learn to write better with AI-powered guidance. Get structured outlines, drafts, and feedback tailored to your coursework.
              </p>
              <div className="flex flex-col sm:flex-row gap-4">
                <Link to="/register">
                  <Button className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm px-8 py-6 text-base transition-lift shadow-sm" data-testid="hero-cta">
                    Start Writing <ArrowRight className="ml-2 w-5 h-5" />
                  </Button>
                </Link>
                <Link to="#pricing">
                  <Button variant="outline" className="border-primary text-primary hover:bg-primary/5 rounded-sm px-8 py-6 text-base" data-testid="view-pricing-btn">
                    View Pricing
                  </Button>
                </Link>
              </div>
            </div>
            <div className="hidden lg:block animate-fade-in-up animation-delay-200">
              <img 
                src="https://images.unsplash.com/photo-1741699427799-3fbb70fce948?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2OTV8MHwxfHNlYXJjaHwxfHxzdHVkZW50JTIwd3JpdGluZyUyMG9uJTIwbGFwdG9wJTIwaW4lMjBsaWJyYXJ5fGVufDB8fHx8MTc3MDU0NzQ4OHww&ixlib=rb-4.1.0&q=85" 
                alt="Student studying in library"
                className="rounded-sm shadow-lg w-full h-auto object-cover"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-6 md:px-12 lg:px-24 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-2xl md:text-3xl font-semibold text-foreground mb-4" style={{ fontFamily: 'Fraunces, serif' }}>
              Why Choose Scholar?
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              A modern approach to academic writing assistance that prioritizes learning and improvement.
            </p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            {features.map((feature, index) => (
              <Card 
                key={index} 
                className="bg-white border border-border/40 hover:border-primary/20 transition-colors p-6 rounded-sm"
                data-testid={`feature-card-${index}`}
              >
                <CardContent className="p-0">
                  <div className="w-12 h-12 bg-secondary rounded-sm flex items-center justify-center mb-4 text-primary">
                    {feature.icon}
                  </div>
                  <h3 className="text-lg font-semibold text-foreground mb-2" style={{ fontFamily: 'Fraunces, serif' }}>
                    {feature.title}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {feature.description}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-20 px-6 md:px-12 lg:px-24 bg-paper">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-2xl md:text-3xl font-semibold text-foreground mb-4" style={{ fontFamily: 'Fraunces, serif' }}>
              Simple, Transparent Pricing
            </h2>
            <p className="text-muted-foreground">
              Pay only for what you need. No subscriptions, no hidden fees.
            </p>
          </div>

          <Card className="bg-white border border-border rounded-sm overflow-hidden" data-testid="pricing-calculator">
            <CardContent className="p-8">
              <div className="grid md:grid-cols-2 gap-8">
                <div>
                  <h3 className="text-lg font-semibold mb-4" style={{ fontFamily: 'Fraunces, serif' }}>
                    Calculate Your Price
                  </h3>
                  <label className="block text-sm text-muted-foreground mb-2">
                    Word Count
                  </label>
                  <input
                    type="range"
                    min="280"
                    max="20000"
                    step="280"
                    value={wordCount}
                    onChange={(e) => setWordCount(parseInt(e.target.value))}
                    className="w-full h-2 bg-secondary rounded-lg appearance-none cursor-pointer accent-primary"
                    data-testid="word-count-slider"
                  />
                  <div className="flex justify-between mt-2 text-sm text-muted-foreground">
                    <span>280</span>
                    <span className="font-mono font-medium text-foreground">{wordCount.toLocaleString()} words</span>
                    <span>20,000</span>
                  </div>

                  <div className="mt-6 space-y-3">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Pages (~280 words each)</span>
                      <span className="font-mono">{pricing.pages}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Price per page</span>
                      <span className="font-mono">$7.00</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Base price</span>
                      <span className="font-mono">${pricing.basePrice}</span>
                    </div>
                    {pricing.hasDiscount && (
                      <div className="flex justify-between text-accent">
                        <span>10% bulk discount</span>
                        <span className="font-mono">-${pricing.discount}</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="bg-secondary/50 rounded-sm p-6 flex flex-col justify-center items-center">
                  <p className="text-sm text-muted-foreground mb-2">Your Total</p>
                  <p className="font-mono text-4xl font-bold text-primary" data-testid="total-price">
                    ${pricing.finalPrice}
                  </p>
                  {pricing.hasDiscount && (
                    <span className="mt-2 inline-flex items-center px-3 py-1 bg-accent/10 text-accent text-sm rounded-full">
                      <CheckCircle className="w-4 h-4 mr-1" /> 10% saved!
                    </span>
                  )}
                  <p className="text-xs text-muted-foreground mt-4 text-center">
                    Orders over 10,000 words get 10% off
                  </p>
                </div>
              </div>

              <div className="mt-8 pt-6 border-t border-border">
                <Link to="/register" className="block">
                  <Button className="w-full bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm py-6 text-base" data-testid="pricing-cta">
                    Get Started Now <ArrowRight className="ml-2 w-5 h-5" />
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-20 px-6 md:px-12 lg:px-24 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-2xl md:text-3xl font-semibold text-foreground mb-4" style={{ fontFamily: 'Fraunces, serif' }}>
              How It Works
            </h2>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { step: "1", title: "Describe Your Assignment", desc: "Enter your requirements, subject, and word count. Upload any course materials for context." },
              { step: "2", title: "Pay Securely", desc: "Complete your payment via Stripe. Your assignment goes into the queue immediately." },
              { step: "3", title: "Get Your Content", desc: "AI generates your academic writing. Download, review, and learn from the structure." }
            ].map((item, index) => (
              <div key={index} className="text-center" data-testid={`step-${item.step}`}>
                <div className="w-12 h-12 bg-primary text-primary-foreground rounded-full flex items-center justify-center mx-auto mb-4 text-xl font-semibold">
                  {item.step}
                </div>
                <h3 className="text-lg font-semibold mb-2" style={{ fontFamily: 'Fraunces, serif' }}>
                  {item.title}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-6 md:px-12 lg:px-24 bg-primary text-primary-foreground">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="flex items-center gap-2">
              <BookOpen className="w-6 h-6" strokeWidth={1.5} />
              <span className="text-lg font-semibold" style={{ fontFamily: 'Fraunces, serif' }}>Scholar</span>
            </div>
            <p className="text-sm text-primary-foreground/70">
              © 2024 Scholar. Academic writing assistance for better learning.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
