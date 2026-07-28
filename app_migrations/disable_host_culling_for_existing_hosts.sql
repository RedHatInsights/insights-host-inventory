UPDATE hosts 
SET 
    stale_timestamp = '5100-06-12T16:52:29.025368+00:00',
    deletion_timestamp = '5100-06-12T16:52:29.025368+00:00',
    stale_warning_timestamp = '5100-06-12T16:52:29.025368+00:00',
    per_reporter_staleness = jsonb_set(
        jsonb_set(
            jsonb_set(
                per_reporter_staleness, 
                '{stale_timestamp}', 
                '"5100-06-12T16:52:29.025368+00:00"'
            ),
            '{deletion_timestamp}', 
            '"5100-06-12T16:52:29.025368+00:00"'
        ),
        '{stale_warning_timestamp}', 
        '"5100-06-12T16:52:29.025368+00:00"'
    );