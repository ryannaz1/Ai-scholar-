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
  const [uploadedFiles, setUploadedFiles] = useState([]); // {id, name, category}
  const [assignmentId, setAssignmentId] = useState(null);
  
  const [formData, setFormData] = useState({
    title: '',
    subject: '',
    requirements: '',
    word_count: 1000,
    writing_style: 'academic',
    additional_notes: '',
    assignment_format: 'general',
    concert_structure: 'single_work',
    has_conductor: null,
    citation_style: 'apa',
  });

  const calculatePrice = (words) => {
    const w = parseInt(words) || 0;
    const pages = w / 280;
    const basePrice = pages * 7;
    const discount = w >= 10000 ? basePrice * 0.1 : 0;
    return {
      pages: pages.toFixed(1),
      basePrice: basePrice.toFixed(2),
      discount: discount.toFixed(2),
      finalPrice: (basePrice - discount).toFixed(2),
      hasDiscount: w >= 10000
    };
  };

  const pricing = calculatePrice(formData.word_count);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleWordCountChange = (e) => {
    const rawValue = e.target.value;
    // Allow empty value during typing
    if (rawValue === '') {
      setFormData(prev => ({ ...prev, word_count: '' }));
      return;
    }
    const value = parseInt(rawValue);
    if (isNaN(value) || value < 1) {
      setFormData(prev => ({ ...prev, word_count: '' }));
      return;
    }
    // Allow any positive number up to 50k. Pricing minimum applies separately.
    const clampedValue = Math.min(50000, value);
    setFormData(prev => ({ ...prev, word_count: clampedValue }));
  };

  const handleFileUpload = async (e, category = 'course_material') => {
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
      formDataUpload.append('category', category);

      try {
        const res = await axios.post(
          `${API}/assignments/${currentAssignmentId}/upload`,
          formDataUpload,
          { headers: { 'Content-Type': 'multipart/form-data' } }
        );
        setUploadedFiles(prev => [...prev, { id: res.data.id, name: file.name, category }]);
        toast.success(`${file.name} uploaded`);
      } catch (error) {
        const msg = error.response?.data?.detail || `Failed to upload ${file.name}`;
        toast.error(msg);
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
    const wc = parseInt(formData.word_count);
    if (!wc || wc < 1) {
      toast.error('Enter a valid word count (at least 1)');
      return;
    }
    // Normalize before submit
    const payload = { ...formData, word_count: wc };

    setLoading(true);

    try {
      let currentAssignmentId = assignmentId;
      
      // Create assignment if not already created
      if (!currentAssignmentId) {
        const res = await axios.post(`${API}/assignments`, payload);
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
            <span className="text-lg font-semibold text-primary" style={{ fontFamily: 'Fraunces, serif' }}>AIScholar</span>
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
                        min="1"
                        max="50000"
                        step="1"
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

                  {/* Assignment Format */}
                  <div className="space-y-2">
                    <Label htmlFor="assignment_format">Assignment Format</Label>
                    <Select
                      value={formData.assignment_format}
                      onValueChange={(value) => setFormData(prev => ({ ...prev, assignment_format: value }))}
                    >
                      <SelectTrigger className="rounded-sm" data-testid="format-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="general">General Academic Essay</SelectItem>
                        <SelectItem value="concert_report">Concert Report</SelectItem>
                        <SelectItem value="lab_report">Lab Report</SelectItem>
                        <SelectItem value="literature_review">Literature Review</SelectItem>
                        <SelectItem value="case_study">Case Study</SelectItem>
                        <SelectItem value="masters_thesis">Master's Thesis (chapter) ⭐</SelectItem>
                        <SelectItem value="masters_thesis_proposal">Master's Thesis Proposal ⭐</SelectItem>
                        <SelectItem value="dissertation">Doctoral Dissertation (chapter)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Concert Report — conditional intake */}
                  {formData.assignment_format === 'concert_report' && (
                    <div className="space-y-3 p-4 bg-secondary/30 border border-border/40 rounded-sm" data-testid="concert-fields">
                      <p className="text-sm font-medium" style={{ fontFamily: 'Fraunces, serif' }}>Concert Report Details</p>
                      <div className="space-y-2">
                        <Label className="text-sm">Program structure</Label>
                        <Select
                          value={formData.concert_structure || 'single_work'}
                          onValueChange={(value) => setFormData(prev => ({ ...prev, concert_structure: value }))}
                        >
                          <SelectTrigger className="rounded-sm" data-testid="concert-structure-select">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="single_work">Single Major Work (one piece in depth)</SelectItem>
                            <SelectItem value="multiple_pieces">Multiple Pieces (full program)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-sm">Conductor present?</Label>
                        <Select
                          value={formData.has_conductor === null ? 'unknown' : (formData.has_conductor ? 'yes' : 'no')}
                          onValueChange={(value) => setFormData(prev => ({
                            ...prev,
                            has_conductor: value === 'yes' ? true : value === 'no' ? false : null,
                          }))}
                        >
                          <SelectTrigger className="rounded-sm" data-testid="conductor-select">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="yes">Yes — there's a conductor</SelectItem>
                            <SelectItem value="no">No — chamber / no conductor</SelectItem>
                            <SelectItem value="unknown">Not sure / not specified</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  )}

                  {/* Citation Style */}
                  <div className="space-y-2">
                    <Label htmlFor="citation_style">Citation Style</Label>
                    <Select
                      value={formData.citation_style}
                      onValueChange={(value) => setFormData(prev => ({ ...prev, citation_style: value }))}
                    >
                      <SelectTrigger className="rounded-sm" data-testid="citation-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="apa">APA (7th edition)</SelectItem>
                        <SelectItem value="mla">MLA (9th edition)</SelectItem>
                        <SelectItem value="harvard">Harvard</SelectItem>
                        <SelectItem value="chicago">Chicago / Turabian</SelectItem>
                        <SelectItem value="ieee">IEEE (numeric)</SelectItem>
                        <SelectItem value="none">No citations needed</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-[11px] text-muted-foreground">
                      The draft will include cover page, table of contents, in-text citations in this style, references, and appendix.
                    </p>
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

              {/* File Upload — 3 categorized zones */}
              <Card className="bg-white border border-border/40 rounded-sm" data-testid="upload-card">
                <CardHeader>
                  <CardTitle className="text-lg" style={{ fontFamily: 'Fraunces, serif' }}>Supporting Documents</CardTitle>
                  <CardDescription>
                    Categorize uploads so the AI uses each kind of context correctly (all optional).
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {[
                    { key: 'requirements', label: 'Assignment Brief / Requirements', hint: 'Rubric, prompt sheet, instructions from your professor' },
                    { key: 'course_material', label: 'Course Material', hint: 'Syllabus, readings, lecture notes, slides' },
                    { key: 'previous_assignment', label: 'Your Previous Work', hint: 'Past graded work — used to subtly match your voice (never copied)' },
                  ].map(zone => {
                    const filesInZone = uploadedFiles.filter(f => f.category === zone.key);
                    return (
                      <div key={zone.key} data-testid={`upload-zone-${zone.key}`}>
                        <div className="flex items-baseline justify-between mb-1">
                          <Label className="text-sm font-medium">{zone.label}</Label>
                          <span className="text-xs text-muted-foreground">{filesInZone.length} file{filesInZone.length === 1 ? '' : 's'}</span>
                        </div>
                        <p className="text-xs text-muted-foreground mb-2">{zone.hint}</p>
                        <div className="border-2 border-dashed border-border rounded-sm p-4 text-center hover:border-primary/40 transition-colors">
                          <input
                            type="file"
                            id={`file-upload-${zone.key}`}
                            multiple
                            accept=".pdf,.docx,.doc,.txt"
                            onChange={(e) => handleFileUpload(e, zone.key)}
                            className="hidden"
                            data-testid={`file-input-${zone.key}`}
                          />
                          <label
                            htmlFor={`file-upload-${zone.key}`}
                            className="cursor-pointer flex flex-col items-center"
                          >
                            {uploadingFile ? (
                              <Loader2 className="w-6 h-6 text-muted-foreground animate-spin mb-1" />
                            ) : (
                              <Upload className="w-6 h-6 text-muted-foreground mb-1" />
                            )}
                            <span className="text-xs font-medium">
                              {uploadingFile ? 'Uploading…' : 'Click or drop files'}
                            </span>
                            <span className="text-[10px] text-muted-foreground mt-0.5">PDF, DOCX, TXT · max 10MB</span>
                          </label>
                        </div>
                        {filesInZone.length > 0 && (
                          <div className="mt-2 space-y-1">
                            {filesInZone.map((file) => (
                              <div
                                key={file.id}
                                className="flex items-center justify-between p-2 bg-secondary/50 rounded-sm text-sm"
                                data-testid={`uploaded-file-${file.id}`}
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <FileText className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                                  <span className="truncate">{file.name}</span>
                                  <CheckCircle className="w-3.5 h-3.5 text-green-600 flex-shrink-0" />
                                </div>
                                <button
                                  type="button"
                                  onClick={() => removeFile(file.id)}
                                  className="text-muted-foreground hover:text-foreground flex-shrink-0 ml-2"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
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
                      <span className="font-mono">{(formData.word_count || 0).toLocaleString()}</span>
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
