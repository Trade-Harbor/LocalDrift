import { useState } from 'react';
import axios from 'axios';
import { Flag, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from './ui/button';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from './ui/dialog';
import { Textarea } from './ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select';
import { useAuth } from '../context/AuthContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const REASONS = [
  { value: 'spam', label: 'Spam or repetitive content' },
  { value: 'abuse', label: 'Harassment or abuse' },
  { value: 'inappropriate', label: 'Inappropriate / offensive content' },
  { value: 'misinformation', label: 'False information' },
  { value: 'other', label: 'Something else' },
];

// Human-friendly singular noun for the dialog title. Falls back to the
// raw target_type if a new type slips in without a label.
const TARGET_LABEL = {
  post: 'post',
  comment: 'comment',
  event: 'event',
  user: 'user',
  creator: 'community source',
};

/**
 * A small flag-icon button that opens a "Report this" dialog.
 *
 * Props:
 *   targetType: 'post' | 'comment' | 'event'
 *   targetId:   id of the target row
 *   variant:    'icon' (just the flag) or 'text' (flag + label) — default 'icon'
 *   className:  additional classes for the trigger button
 *
 * Auth: uses the AuthContext token. If the user isn't signed in we still
 * show the button (so it's discoverable) but route them to /login on click.
 */
export default function ReportButton({ targetType, targetId, variant = 'icon', className = '' }) {
  const { isAuthenticated, token } = useAuth();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [details, setDetails] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleClick = (e) => {
    e.stopPropagation();
    if (!isAuthenticated) {
      toast.error('Sign in to report content');
      return;
    }
    setOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!reason) {
      toast.error('Pick a reason');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(
        `${API_URL}/api/reports`,
        { target_type: targetType, target_id: targetId, reason, details: details.trim() || null },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Thanks — we\'ll review it.');
      setOpen(false);
      setReason('');
      setDetails('');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not submit report');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={handleClick}
        className={`text-muted-foreground hover:text-red-500 ${className}`}
        data-testid={`report-${targetType}-${targetId}`}
      >
        <Flag className="h-4 w-4" />
        {variant === 'text' && <span className="ml-1">Report</span>}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent onClick={(e) => e.stopPropagation()}>
          <DialogHeader>
            <DialogTitle>Report this {TARGET_LABEL[targetType] || targetType}</DialogTitle>
            <DialogDescription>
              Help keep LocalDrift welcoming. We'll review the report and take action if needed.
              False reports may affect your account.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1 block">Reason</label>
              <Select value={reason} onValueChange={setReason}>
                <SelectTrigger data-testid="report-reason">
                  <SelectValue placeholder="Pick one" />
                </SelectTrigger>
                <SelectContent>
                  {REASONS.map((r) => (
                    <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">
                Details <span className="text-muted-foreground">(optional)</span>
              </label>
              <Textarea
                value={details}
                onChange={(e) => setDetails(e.target.value)}
                placeholder="Anything else we should know?"
                rows={3}
                maxLength={1000}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting || !reason}>
                {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                Submit report
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
