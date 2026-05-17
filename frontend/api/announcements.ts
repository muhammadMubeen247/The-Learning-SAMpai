import api from "./axios";

export interface AnnouncementComment {
  id: number;
  announcement_id: number;
  created_by_id: number;
  created_by_username: string;
  content: string;
  created_at: string;
}

export interface Announcement {
  id: number;
  classroom_id: number;
  created_by_id: number;
  created_by_username: string;
  content: string; // HTML
  created_at: string;
  updated_at: string;
  comments: AnnouncementComment[];
}

export const announcementsApi = {
  list: (classroomId: number): Promise<Announcement[]> =>
    api.get(`/announcements/classrooms/${classroomId}`).then((r) => r.data),

  create: (classroomId: number, content: string): Promise<Announcement> =>
    api
      .post(`/announcements/classrooms/${classroomId}`, { content })
      .then((r) => r.data),

  delete: (announcementId: number): Promise<void> =>
    api
      .delete(`/announcements/announcements/${announcementId}`)
      .then(() => undefined),

  addComment: (
    announcementId: number,
    content: string
  ): Promise<AnnouncementComment> =>
    api
      .post(`/announcements/announcements/${announcementId}/comments`, {
        content,
      })
      .then((r) => r.data),

  deleteComment: (
    announcementId: number,
    commentId: number
  ): Promise<void> =>
    api
      .delete(
        `/announcements/announcements/${announcementId}/comments/${commentId}`
      )
      .then(() => undefined),
};
