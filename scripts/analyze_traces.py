#!/usr/bin/env python3
import sys, json
from collections import defaultdict

# Read data from stdin
data = json.load(sys.stdin)
print(f'Total log events: {len(data)}')

# Look for unique trace IDs
trace_ids = set()
trace_timestamps = defaultdict(list)

for event in data:
    try:
        timestamp = event[0]
        msg = json.loads(event[1])

        if 'attributes' in msg:
            attrs = msg['attributes']
            if 'otelTraceID' in attrs and attrs['otelTraceID'] != '0' and attrs['otelTraceID'] != '':
                trace_id = attrs['otelTraceID']
                trace_ids.add(trace_id)
                trace_timestamps[trace_id].append(timestamp)
    except Exception as e:
        pass

print(f'\nUnique trace IDs found: {len(trace_ids)}')
for tid in sorted(trace_ids):
    timestamps = trace_timestamps[tid]
    print(f'  - Trace ID: {tid}')
    print(f'    Events: {len(timestamps)}')
    if timestamps:
        import datetime
        start_ms = min(timestamps)
        end_ms = max(timestamps)
        duration_ms = end_ms - start_ms
        duration_sec = duration_ms / 1000.0

        start = datetime.datetime.fromtimestamp(start_ms/1000)
        end = datetime.datetime.fromtimestamp(end_ms/1000)
        print(f'    Time range: {start} to {end}')
        print(f'    Duration: {duration_sec:.3f}s ({duration_ms}ms)')
