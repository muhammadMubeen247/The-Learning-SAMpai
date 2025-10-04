import API from "./axios";

// Create classroom
export const createClassroom = async (data) => {
  const res = await API.post("/classrooms/create", data);
  return res.data;
};

// Join classroom
export const joinClassroom = async (code) => {
  const res = await API.post(`/classrooms/join/${code}`);
  return res.data;
};

// Get my classrooms
export const getMyClassrooms = async () => {
  const res = await API.get("/classrooms/");
  return res.data;
};
