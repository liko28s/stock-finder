You are reviewing a past alert for an advisory stock screener. Be honest: if the evidence does not
support the human's report or the original call, say so.

Alert: #{ticker} {signal} (confidence {confidence}), sent {sent}, entry reference close {entry}.
Original reasoning: {reasoning}
Data at signal time:
{signal_data}

Human reported: {outcome}.
Price path since the alert (daily bars):
{bars}
Computed from the path (percent vs entry, in the direction of the call): best move {mfe:+.1f}% on {mfe_day}, worst move {mae:+.1f}% on {mae_day}, latest close {last:+.1f}%.
Indicators now:
{now_data}

Use ONLY the numbers above; quote them. Reply with a single JSON object, no prose, with exactly these keys:
  "assessment": "good_call" | "bad_call" | "lucky" | "unlucky" | "inconclusive"
  "what_happened": 3-5 sentences: which signal-time indicators held or failed, and the events in the path that led to the reported outcome
  "adjustments": list of 0-3 concrete threshold or indicator changes worth testing (strings)
