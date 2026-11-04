import React from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { CalendarDays, Clock, MapPin, Pencil, Sparkles } from "lucide-react";

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(`${value}T12:00:00`);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("fr-FR", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
}

export default function EventDetailsDialog({ open, onOpenChange, event, canEdit = false, onEdit }) {
  if (!event) return null;
  const time = event.start_time
    ? `${event.start_time}${event.end_time ? ` – ${event.end_time}` : ""}`
    : "Journée";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto" data-testid="event-details-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl flex items-start gap-2">
            <Sparkles size={18} className="mt-1 shrink-0 text-violet-500" />
            <span data-testid="event-details-title">{event.title}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          <div className="flex items-center gap-2 text-slate-700">
            <CalendarDays size={16} className="text-violet-500" />
            <span data-testid="event-details-date">{formatDate(event.date)}</span>
          </div>
          <div className="flex items-center gap-2 text-slate-700">
            <Clock size={16} className="text-violet-500" />
            <span data-testid="event-details-time">{time}</span>
          </div>
          {event.location && (
            <div className="flex items-start gap-2 text-slate-700">
              <MapPin size={16} className="mt-0.5 shrink-0 text-violet-500" />
              <span data-testid="event-details-location" className="whitespace-pre-wrap">{event.location}</span>
            </div>
          )}
          {event.description && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-slate-700 whitespace-pre-wrap" data-testid="event-details-description">
              {event.description}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="event-details-close">Fermer</Button>
          {canEdit && (
            <Button onClick={onEdit} data-testid="event-details-edit">
              <Pencil size={14} className="mr-1.5" /> Modifier
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
