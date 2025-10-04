import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import API from "../api/axios";

export default function ClassroomPage() {
  const { id } = useParams(); // get classroom id from URL
  const [classroom, setClassroom] = useState(null);

  useEffect(() => {
    fetchClassroom();
  }, [id]);

  const fetchClassroom = async () => {
    try {
      const res = await API.get(`/classrooms/${id}`);
      setClassroom(res.data);
    } catch (err) {
      console.error("Error fetching classroom:", err);
    }
  };

  if (!classroom) return <p className="p-6">Loading classroom...</p>;

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h2 className="text-2xl font-bold mb-2">{classroom.name}</h2>
      <p className="text-gray-600 mb-4">{classroom.description}</p>
      <p className="text-sm text-gray-500 mb-6">Code: {classroom.code}</p>

      <h3 className="text-xl font-semibold mb-2">Members</h3>
      <ul className="list-disc list-inside">
        {classroom.members.map((m) => (
          <li key={m.id}>
            {m.username} <span className="text-gray-500">({m.email})</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
