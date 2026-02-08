import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { 
  BookOpen, ArrowLeft, Upload, FileText, X, 
  Loader2, CheckCircle, Info
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const NewAssignment = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [uploadingFile, setUploadingFile] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [assignmentId, setAssignmentId] = useState(null);
  
  const [formData, setFormData] = useState({
    title: '',
    subject: '',
    requirements: '',
    word_count: 1000,
    writing_style: 'academic',
    additional_notes: ''
  });

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

  const pricing = calculatePrice(formData.word_count);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleWordCountChange = (e) => {
    const value = Math.max(280, Math.min(50000, parseInt(e.target.value) || 280));
    setFormData(prev => ({ ...prev, word_count: value }));
  };

  const handleFileUpload = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // If no assignment created yet, create one first
    let currentAssignmentId = assignmentId;
    if (!currentAssignmentId) {
      if (!formData.title || !formData.subject || !formData.requirements) {
        toast.error('Please fill in title, subject, and requirements before uploading files');
        return;
      }

      try {
        setLoading(true);
        const res = await axios.post(`${API}/assignments`, formData);
        currentAssignmentId = res.data.id;
        setAssignmentId(currentAssignmentId);
      } catch (error) {
        toast.error('Failed to create assignment');
        setLoading(false);
        return;
      }
      setLoading(false);
    }

    // Upload files
    for (const file of files) {
      setUploadingFile(true);
      const formDataUpload = new FormData();
      formDataUpload.append('file', file);

      try {
        const res = await axios.post(
          `${API}/assignments/${currentAssignmentId}/upload`,
          formDataUpload,
          { headers: { 'Content-Type': 'multipart/form-data' } }
        );
        setUploadedFiles(prev => [...prev, { id: res.data.id, name: file.name }]);
        toast.success(`${file.name} uploaded successfully`);
      } catch (error) {
        toast.error(`Failed to upload ${file.name}`);
      } finally {
        setUploadingFile(false);
      }
    }

    e.target.value = '';
  };

  const removeFile = (fileId) => {
    setUploadedFiles(prev => prev.filter(f => f.id !== fileId));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.title || !formData.subject || !formData.requirements) {
      toast.error('Please fill in all required fields');
      return;
    }

    setLoading(true);

    try {
      let currentAssignmentId = assignmentId;
      
      // Create assignment if not already created
      if (!currentAssignmentId) {
        const res = await axios.post(`${API}/assignments`, formData);
        currentAssignmentId = res.data.id;
        setAssignmentId(currentAssignmentId);
      }

      // Navigate to assignment detail/payment page
      navigate(`/assignment/${currentAssignmentId}`);
      
    } catch (error) {
      const message = error.response?.data?.detail || 'Failed to create assignment';
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const writingStyles = [
    { value: 'academic', label: 'Academic / Scholarly' },
    { value: 'analytical', label: 'Analytical / Critical' },
    { value: 'argumentative', label: 'Argumentative / Persuasive' },
    { value: 'descriptive', label: 'Descriptive / Narrative' },
    { value: 'expository', label: 'Expository / Informative' },
    { value: 'research', label: 'Research Paper' }
  ];

  const subjects = [
    'English Literature', 'History', 'Psychology', 'Sociology', 
    'Business', 'Economics', 'Political Science', 'Philosophy',
    'Biology', 'Chemistry', 'Physics', 'Computer Science',
    'Education', 'Nursing', 'Law', 'Other'
  ];

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
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-semibold text-foreground" style={{ fontFamily: 'Fraunces, serif' }}>
            New Assignment
          </h1>
          <p className="text-muted-foreground mt-1">
            Describe your assignment requirements and upload any course materials.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="grid lg:grid-cols-3 gap-8">
            {/* Main Form */}
            <div className="lg:col-span-2 space-y-6">
              <Card className="bg-white border border-border/40 rounded-sm" data-testid="assignment-form-card">
                <CardHeader>
                  <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>Assignment Details</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Title */}
                  <div className="space-y-2">
                    <Label htmlFor="title">Assignment Title *</Label>
                    <Input
                      id="title"
                      name="title"
                      placeholder="e.g., Analysis of Shakespeare's Hamlet"
                      value={formData.title}
                      onChange={handleChange}
                      className="rounded-sm"
                      data-testid="title-input"
                      required
                    />
                  </div>

                  {/* Subject */}
                  <div className="space-y-2">
                    <Label htmlFor="subject">Subject *</Label>
                    <Select 
                      value={formData.subject} 
                      onValueChange={(value) => setFormData(prev => ({ ...prev, subject: value }))}
                    >
                      <SelectTrigger className="rounded-sm" data-testid="subject-select">
                        <SelectValue placeholder="Select a subject" />
                      </SelectTrigger>
                      <SelectContent>
                        {subjects.map(subject => (
                          <SelectItem key={subject} value={subject}>{subject}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Requirements */}
                  <div className="space-y-2">
                    <Label htmlFor="requirements">Requirements & Instructions *</Label>
                    <Textarea
                      id="requirements"
                      name="requirements"
                      placeholder="Describe your assignment requirements in detail. Include any specific topics to cover, questions to answer, formatting requirements, etc."
                      value={formData.requirements}
                      onChange={handleChange}
                      className="rounded-sm min-h-[150px]"
                      data-testid="requirements-input"
                      required
                    />
                  </div>

                  {/* Word Count */}
                  <div className="space-y-2">
                    <Label htmlFor="word_count">Target Word Count *</Label>
                    <div className="flex items-center gap-4">
                      <Input
                        id="word_count"
                        name="word_count"
                        type="number"
                        min="280"
                        max="50000"
                        step="100"
                        value={formData.word_count}
                        onChange={handleWordCountChange}
                        className="rounded-sm w-32"
                        data-testid="word-count-input"
                        required
                      />
                      <span className="text-sm text-muted-foreground">
                        (~{pricing.pages} pages)
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Minimum 280 words (1 page). 10% discount on orders over 10,000 words.
                    </p>
                  </div>

                  {/* Writing Style */}
                  <div className="space-y-2">
                    <Label htmlFor="writing_style">Writing Style</Label>
                    <Select 
                      value={formData.writing_style} 
                      onValueChange={(value) => setFormData(prev => ({ ...prev, writing_style: value }))}
                    >
                      <SelectTrigger className="rounded-sm" data-testid="style-select">
                        <SelectValue placeholder="Select writing style" />
                      </SelectTrigger>
                      <SelectContent>
                        {writingStyles.map(style => (
                          <SelectItem key={style.value} value={style.value}>{style.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Additional Notes */}
                  <div className="space-y-2">
                    <Label htmlFor="additional_notes">Additional Notes (Optional)</Label>
                    <Textarea
                      id="additional_notes"
                      name="additional_notes"
                      placeholder="Any other information that might help (preferred sources, specific arguments to include, etc.)"
                      value={formData.additional_notes}
                      onChange={handleChange}
                      className="rounded-sm min-h-[80px]"
                      data-testid="notes-input"
                    />
                  </div>
                </CardContent>
              </Card>

              {/* File Upload */}
              <Card className="bg-white border border-border/40 rounded-sm" data-testid="upload-card">
                <CardHeader>
                  <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>Course Materials</CardTitle>
                  <CardDescription>
                    Upload syllabus, readings, or previous assignments for context (optional)
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="border-2 border-dashed border-border rounded-sm p-8 text-center">
                    <input
                      type="file"
                      id="file-upload"
                      multiple
                      accept=".pdf,.docx,.doc,.txt"
                      onChange={handleFileUpload}
                      className="hidden"
                      data-testid="file-input"
                    />
                    <label
                      htmlFor="file-upload"
                      className="cursor-pointer flex flex-col items-center"
                    >
                      {uploadingFile ? (
                        <Loader2 className="w-10 h-10 text-muted-foreground animate-spin mb-3" />
                      ) : (
                        <Upload className="w-10 h-10 text-muted-foreground mb-3" />
                      )}
                      <span className="text-sm font-medium">
                        {uploadingFile ? 'Uploading...' : 'Click to upload or drag and drop'}
                      </span>
                      <span className="text-xs text-muted-foreground mt-1">
                        PDF, DOCX, DOC, TXT (max 10MB each)
                      </span>
                    </label>
                  </div>

                  {/* Uploaded Files */}
                  {uploadedFiles.length > 0 && (
                    <div className="mt-4 space-y-2">
                      {uploadedFiles.map((file) => (
                        <div
                          key={file.id}
                          className="flex items-center justify-between p-3 bg-secondary/50 rounded-sm"
                          data-testid={`uploaded-file-${file.id}`}
                        >
                          <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4 text-primary" />
                            <span className="text-sm">{file.name}</span>
                            <CheckCircle className="w-4 h-4 text-green-600" />
                          </div>
                          <button
                            type="button"
                            onClick={() => removeFile(file.id)}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Pricing Sidebar */}
            <div className="lg:col-span-1">
              <Card className="bg-white border border-border/40 rounded-sm sticky top-8" data-testid="pricing-sidebar">
                <CardHeader>
                  <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>Order Summary</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Word count</span>
                      <span className="font-mono">{formData.word_count.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Pages (~280 words)</span>
                      <span className="font-mono">{pricing.pages}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Price per page</span>
                      <span className="font-mono">$7.00</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Subtotal</span>
                      <span className="font-mono">${pricing.basePrice}</span>
                    </div>
                    {pricing.hasDiscount && (
                      <div className="flex justify-between text-accent">
                        <span>Bulk discount (10%)</span>
                        <span className="font-mono">-${pricing.discount}</span>
                      </div>
                    )}
                  </div>

                  <div className="border-t border-border pt-4">
                    <div className="flex justify-between items-center">
                      <span className="font-semibold">Total</span>
                      <span className="font-mono text-2xl font-bold text-primary" data-testid="order-total">
                        ${pricing.finalPrice}
                      </span>
                    </div>
                  </div>

                  {pricing.hasDiscount && (
                    <div className="flex items-center gap-2 p-3 bg-accent/10 rounded-sm text-accent text-sm">
                      <CheckCircle className="w-4 h-4 flex-shrink-0" />
                      <span>10% bulk discount applied!</span>
                    </div>
                  )}

                  <div className="flex items-start gap-2 p-3 bg-secondary/50 rounded-sm text-sm text-muted-foreground">
                    <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <span>Your content will be ready after payment. AI generates academic writing to help you learn.</span>
                  </div>

                  <Button
                    type="submit"
                    className="w-full bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm py-5"
                    disabled={loading}
                    data-testid="proceed-btn"
                  >
                    {loading ? (
                      <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    ) : null}
                    Continue to Payment
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>
        </form>
      </main>
    </div>
  );
};

export default NewAssignment;
