/**
 * AthleteSearchSelector.jsx — Searchable athlete selector with recents (PR-163)
 *
 * Props:
 *   athletes  — [{ id, first_name, last_name, email }]
 *   value     — 'a:42' | ''
 *   onChange  — (value: string) => void
 *   loading   — boolean
 *   pmcMap    — { [athleteId]: { ctl } } optional CTL badges
 */
import React, { useMemo } from 'react';
import { Box, Typography } from '@mui/material';
import { Autocomplete, TextField } from '@mui/material';

const RECENTS_KEY = 'calendarRecentAthletes';
const MAX_RECENTS = 5;

function loadRecents() {
  try {
    return JSON.parse(localStorage.getItem(RECENTS_KEY) ?? '[]');
  } catch {
    return [];
  }
}

function saveRecent(id, name) {
  const prev = loadRecents().filter((r) => r.id !== id);
  const next = [{ id, name }, ...prev].slice(0, MAX_RECENTS);
  try {
    localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
  } catch {
    // ignore storage errors
  }
}

function athleteDisplayName(a) {
  return [a.first_name, a.last_name].filter(Boolean).join(' ') || a.email?.split('@')[0] || `Atleta #${a.id}`;
}

function getInitials(name) {
  return name.split(' ').slice(0, 2).map((w) => w[0]?.toUpperCase() ?? '').join('');
}

export default function AthleteSearchSelector({ athletes = [], value, onChange, loading = false, pmcMap = {} }) {
  const options = useMemo(() => {
    // Read recents inside memo so it stays fresh without becoming a volatile dep
    const recents = loadRecents();

    const athleteOptions = athletes.map((a) => ({
      value: `a:${a.id}`,
      label: athleteDisplayName(a),
      athleteId: a.id,
      isRecent: false,
    }));

    // Inject recents group at top
    const recentOptions = recents
      .map((r) => {
        const found = athletes.find((a) => a.id === r.id);
        if (!found) return null;
        return {
          value: `a:${found.id}`,
          label: athleteDisplayName(found),
          athleteId: found.id,
          isRecent: true,
        };
      })
      .filter(Boolean);

    // Dedupe: recents first, then remaining athletes
    const recentIds = new Set(recentOptions.map((r) => r.value));
    const rest = athleteOptions.filter((o) => !recentIds.has(o.value));

    return [...recentOptions, ...rest];
  }, [athletes]);

  const selected = options.find((o) => o.value === value) ?? null;

  const handleChange = (_e, option) => {
    if (!option) {
      onChange('');
      return;
    }
    saveRecent(option.athleteId, option.label);
    onChange(option.value);
  };

  return (
    <Autocomplete
      options={options}
      value={selected}
      onChange={handleChange}
      getOptionLabel={(o) => o.label}
      isOptionEqualToValue={(o, v) => o.value === v.value}
      disabled={loading}
      groupBy={(o) => o.isRecent ? 'RECIENTES' : 'ATLETAS'}
      noOptionsText="Sin atletas"
      sx={{ minWidth: 240, maxWidth: 320 }}
      renderInput={(params) => (
        <TextField
          {...params}
          size="small"
          label="Buscar atleta…"
          placeholder="🔍 Buscar…"
          InputLabelProps={{ shrink: true }}
        />
      )}
      renderOption={(props, option) => {
        const ctl = pmcMap[option.athleteId]?.ctl;
        const initials = getInitials(option.label);
        return (
          <Box component="li" {...props} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 0.75, px: 2 }}>
            {/* Avatar */}
            <Box
              sx={{
                width: 28, height: 28, borderRadius: '50%',
                bgcolor: '#f97316', display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <Typography sx={{ fontSize: '0.65rem', fontWeight: 700, color: '#fff' }}>
                {initials}
              </Typography>
            </Box>
            <Typography sx={{ fontSize: '0.85rem', flex: 1 }}>{option.label}</Typography>
            {ctl != null && (
              <Box
                sx={{
                  px: 0.75, py: 0.1, borderRadius: 1,
                  bgcolor: '#dbeafe', border: '1px solid #93c5fd',
                  fontSize: '0.6rem', fontWeight: 700, color: '#1d4ed8',
                }}
              >
                CTL {Math.round(ctl)}
              </Box>
            )}
          </Box>
        );
      }}
      renderGroup={(params) => (
        <Box key={params.key}>
          <Typography
            sx={{ px: 2, py: 0.5, fontSize: '0.65rem', fontWeight: 700, color: '#94a3b8', letterSpacing: '0.07em', bgcolor: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}
          >
            {params.group}
          </Typography>
          {params.children}
        </Box>
      )}
    />
  );
}
