import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { 
  BookOpen, Plus, FileText, Clock, DollarSign, 
  BarChart3, LogOut, Menu, X, ChevronRight,
  Sparkles, CheckCircle, AlertCircle, ShieldCheck, Settings as SettingsIcon
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Dashboard = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [stats, setStats] = useState(null);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    fetchData();
    fetchAdminStatus();
  }, []);

  const fetchAdminStatus = async () => {
    try {
      const res = await axios.get(`${API}/auth/me-admin`);
      setIsAdmin(!!res.data.is_admin);
    } catch (e) {
      setIsAdmin(false);
    }
  };

  const fetchData = async () => {
    try {
      const [statsRes, assignmentsRes] = await Promise.all([
        axios.get(`${API}/stats/dashboard`),
        axios.get(`${API}/assignments`)
      ]);
      setStats(statsRes.data);
      setAssignments(assignmentsRes.data);
    } catch (error) {
      console.error('Failed to fetch data:', error);
      toast.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const getStatusBadge = (status) => {
    const statusConfig = {
      draft: { label: 'Draft', className: 'bg-secondary text-muted-foreground' },
      paid: { label: 'Paid', className: 'bg-blue-100 text-blue-800' },
      completed: { label: 'Completed', className: 'bg-green-100 text-green-800' }
    };
    const config = statusConfig[status] || statusConfig.draft;
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  const statCards = [
    { 
      title: 'Total Assignments', 
      value: stats?.total_assignments || 0, 
      icon: <FileText className="w-5 h-5" />,
      color: 'text-primary'
    },
    { 
      title: 'Completed', 
      value: stats?.completed_assignments || 0, 
      icon: <CheckCircle className="w-5 h-5" />,
      color: 'text-green-600'
    },
    { 
      title: 'Total Words', 
      value: (stats?.total_words || 0).toLocaleString(), 
      icon: <BarChart3 className="w-5 h-5" />,
      color: 'text-accent'
    },
    { 
      title: 'Total Spent', 
      value: `$${stats?.total_spent || 0}`, 
      icon: <DollarSign className="w-5 h-5" />,
      color: 'text-primary'
    }
  ];

  return (
    <div className="min-h-screen bg-paper">
      {/* Mobile Sidebar Toggle */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-white rounded-sm shadow-sm border border-border"
        data-testid="sidebar-toggle"
      >
        {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar */}
      <aside 
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-white border-r border-border transform transition-transform duration-200 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0`}
        data-testid="sidebar"
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-6 border-b border-border">
            <Link to="/" className="flex items-center gap-2" data-testid="dashboard-logo">
              <BookOpen className="w-7 h-7 text-primary" strokeWidth={1.5} />
              <span className="text-xl font-semibold text-primary" style={{ fontFamily: 'Fraunces, serif' }}>AIScholar</span>
            </Link>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-2">
            <Link
              to="/dashboard"
              className="flex items-center gap-3 px-4 py-3 rounded-sm bg-secondary text-foreground"
              data-testid="nav-dashboard"
            >
              <BarChart3 className="w-5 h-5" strokeWidth={1.5} />
              Dashboard
            </Link>
            <Link
              to="/new-assignment"
              className="flex items-center gap-3 px-4 py-3 rounded-sm hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-new-assignment"
            >
              <Plus className="w-5 h-5" strokeWidth={1.5} />
              New Assignment
            </Link>
            {isAdmin && (
              <Link
                to="/admin/orders"
                className="flex items-center gap-3 px-4 py-3 rounded-sm hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
                data-testid="nav-admin"
              >
                <ShieldCheck className="w-5 h-5" strokeWidth={1.5} />
                Reviewer Inbox
              </Link>
            )}
            {isAdmin && (
              <Link
                to="/settings"
                className="flex items-center gap-3 px-4 py-3 rounded-sm hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
                data-testid="nav-settings"
              >
                <SettingsIcon className="w-5 h-5" strokeWidth={1.5} />
                Settings
              </Link>
            )}
          </nav>

          {/* User */}
          <div className="p-4 border-t border-border">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center text-primary font-medium">
                {user?.name?.charAt(0)?.toUpperCase() || 'U'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{user?.name || 'User'}</p>
                <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
              </div>
            </div>
            <Button
              variant="outline"
              className="w-full justify-start rounded-sm text-muted-foreground"
              onClick={handleLogout}
              data-testid="logout-btn"
            >
              <LogOut className="w-4 h-4 mr-2" />
              Sign Out
            </Button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="lg:ml-64 p-6 lg:p-8" data-testid="dashboard-main">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold text-foreground" style={{ fontFamily: 'Fraunces, serif' }}>
              Welcome back, {user?.name?.split(' ')[0] || 'there'}!
            </h1>
            <p className="text-muted-foreground mt-1">Here's an overview of your writing projects.</p>
          </div>
          <Link to="/new-assignment">
            <Button className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm" data-testid="new-assignment-btn">
              <Plus className="w-4 h-4 mr-2" />
              New Assignment
            </Button>
          </Link>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {statCards.map((stat, index) => (
            <Card key={index} className="bg-white border border-border/40 rounded-sm" data-testid={`stat-card-${index}`}>
              <CardContent className="p-4 lg:p-6">
                <div className="flex items-center justify-between mb-2">
                  <span className={stat.color}>{stat.icon}</span>
                </div>
                <p className="text-2xl lg:text-3xl font-bold font-mono text-foreground">{stat.value}</p>
                <p className="text-xs lg:text-sm text-muted-foreground mt-1">{stat.title}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Recent Assignments */}
        <Card className="bg-white border border-border/40 rounded-sm" data-testid="assignments-card">
          <CardHeader className="border-b border-border/40">
            <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>Recent Assignments</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? (
              <div className="p-8 text-center text-muted-foreground">Loading...</div>
            ) : assignments.length === 0 ? (
              <div className="p-8 text-center">
                <FileText className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
                <p className="text-muted-foreground mb-4">No assignments yet</p>
                <Link to="/new-assignment">
                  <Button variant="outline" className="rounded-sm" data-testid="empty-new-btn">
                    Create your first assignment
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="divide-y divide-border/40">
                {assignments.slice(0, 5).map((assignment) => (
                  <Link
                    key={assignment.id}
                    to={`/assignment/${assignment.id}`}
                    className="flex items-center justify-between p-4 hover:bg-secondary/50 transition-colors"
                    data-testid={`assignment-${assignment.id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-medium truncate">{assignment.title}</h3>
                        {getStatusBadge(assignment.status)}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {assignment.subject} • {assignment.word_count.toLocaleString()} words • ${assignment.final_price}
                      </p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </main>

      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
};

export default Dashboard;
