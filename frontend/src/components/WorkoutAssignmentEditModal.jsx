/**
 * WorkoutAssignmentEditModal.jsx — PR-145g-fix
 *
 * Wraps WorkoutBuilder for inline assignment snapshot editing.
 * The coach edits a session directly from the calendar without navigating
 * to /library. Save calls PATCH /assignments/<id>/update-snapshot/.
 *
 * Props:
 *   open            boolean
 *   onClose         () => void
 *   assignmentId    number
 *   orgId           number
 *   initialWorkout  object  — PlannedWorkout snapshot (pre-loads the builder)
 *   onSaved         (updatedWorkout) => void
 */

import React, { useState } from 'react';
import { Snackbar, Alert } from '@mui/material';
import WorkoutBuilder from './WorkoutBuilder';
import { updateAssignmentSnapshot } from '../api/assignments';

export default function WorkoutAssignmentEditModal({
  open,
  onClose,
  assignmentId,
  orgId,
  initialWorkout,
  onSaved,
}) {
  const [toast, setToast] = useState(false);

  const handleSnapshotSave = (data) =>
    updateAssignmentSnapshot(orgId, assignmentId, data);

  const handleUpdated = (updatedWorkout) => {
    setToast(true);
    onSaved?.(updatedWorkout);
    onClose();
  };

  return (
    <>
      <WorkoutBuilder
        open={open}
        onClose={onClose}
        orgId={orgId}
        libraryId={null}
        editWorkout={initialWorkout ?? null}
        onSnapshotSave={handleSnapshotSave}
        onUpdated={handleUpdated}
        onSaved={() => {}}
      />
      <Snackbar
        open={toast}
        autoHideDuration={3000}
        onClose={() => setToast(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="success" variant="filled" onClose={() => setToast(false)}>
          Sesión actualizada ✓
        </Alert>
      </Snackbar>
    </>
  );
}
