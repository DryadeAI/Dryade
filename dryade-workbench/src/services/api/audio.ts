// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Audio Meetings API - Audio plugin integration

import { fetchWithAuth } from '../apiClient';

// ============== AUDIO MEETINGS API (Plugin: audio) ==============

export interface AudioMeeting {
  id: number;
  title: string | null;
  status: string;
  store_audio: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface AudioMeetingCreateRequest {
  title?: string;
  store_audio?: boolean;
}

export interface AudioTranscriptSegment {
  id: number;
  speaker_id: string | null;
  text: string | null;
  start_time: number | null;
  end_time: number | null;
  created_at: string;
}

export interface AudioSummaryResponse {
  summary_bullets: Array<{
    id: string;
    text: string;
    source_segment_ids: number[];
  }>;
  action_items: Array<{
    id: string;
    text: string;
    owner?: string | null;
    due?: string | null;
    source_segment_ids: number[];
  }>;
}

export const audioMeetingsApi = {
  createMeeting: async (req: AudioMeetingCreateRequest = {}): Promise<AudioMeeting> => {
    return fetchWithAuth<AudioMeeting>('/audio/meetings', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },

  listMeetings: async (): Promise<AudioMeeting[]> => {
    return fetchWithAuth<AudioMeeting[]>('/audio/meetings');
  },

  getTranscript: async (meetingId: number): Promise<AudioTranscriptSegment[]> => {
    return fetchWithAuth<AudioTranscriptSegment[]>(`/audio/meetings/${meetingId}/transcript`);
  },

  summarizeMeeting: async (meetingId: number): Promise<AudioSummaryResponse> => {
    return fetchWithAuth<AudioSummaryResponse>(`/audio/meetings/${meetingId}/summarize`, {
      method: 'POST',
    });
  },
};
