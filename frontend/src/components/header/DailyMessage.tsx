import { BookOpenText, Sparkles } from "lucide-react";
import { getDailyMessage } from "../../content/dailyMessages";

export default function DailyMessage() {
  const message = getDailyMessage();
  const Icon = message.kind === "versiculo" ? BookOpenText : Sparkles;

  return (
    <div className="ejc-daily-message" title={message.text}>
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="min-w-0">
        <span className="ejc-daily-message-text">{message.text}</span>
        {message.reference && (
          <span className="ejc-daily-message-reference">
            {message.reference}
          </span>
        )}
      </span>
    </div>
  );
}
