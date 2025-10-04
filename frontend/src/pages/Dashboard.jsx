import { useEffect, useState } from "react";
import API from "../api/axios";
import { Link } from "react-router-dom";

export default function Dashboard() {
  const [classrooms, setClassrooms] = useState([]);
  const [newClass, setNewClass] = useState({ name: "", description: "" });
  const [joinCode, setJoinCode] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showJoin, setShowJoin] = useState(false);

  // Fetch user's classrooms
  useEffect(() => {
    fetchClassrooms();
  }, []);

  const fetchClassrooms = async () => {
    try {
      const res = await API.get("/classrooms/");
      setClassrooms(res.data);
    } catch (err) {
      console.error("Error fetching classrooms:", err);
    }
  };

  // Create classroom
  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const res = await API.post("/classrooms/create", newClass);
      setClassrooms([...classrooms, res.data]);
      setNewClass({ name: "", description: "" });
      setShowCreate(false);
    } catch (err) {
      console.error("Error creating classroom:", err);
    }
  };

  // Join classroom
  const handleJoin = async (e) => {
    e.preventDefault();
    try {
      const res = await API.post(`/classrooms/join/${joinCode}`);
      setClassrooms([...classrooms, res.data]);
      setJoinCode("");
      setShowJoin(false);
    } catch (err) {
      console.error("Error joining classroom:", err);
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    window.location.href = "/login";
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <button
          onClick={logout}
          className="bg-red-500 text-white px-4 py-2 rounded"
        >
          Logout
        </button>
      </div>

      {/* Classroom list */}
      <h3 className="text-xl font-semibold mb-4">My Classrooms</h3>
      <div className="grid gap-4">
        {classrooms.length === 0 ? (
          <p className="text-gray-600">You are not in any classrooms yet.</p>
) : (
  classrooms.map((cls) => (
    <Link key={cls.id} to={`/classroom/${cls.id}`}>
      <div className="p-4 border rounded shadow-sm bg-gray-50 hover:bg-gray-100 cursor-pointer">
        <h4 className="font-bold">{cls.name}</h4>
        <p>{cls.description}</p>
        <p className="text-sm text-gray-500">Code: {cls.code}</p>
        <p className="text-sm text-gray-500">
          Members: {cls.members.length}
        </p>
      </div>
    </Link>
  ))
)}
      </div>

      {/* Buttons */}
      <div className="flex gap-4 mt-6">
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="bg-blue-500 text-white px-4 py-2 rounded"
        >
          Create Classroom
        </button>
        <button
          onClick={() => setShowJoin(!showJoin)}
          className="bg-green-500 text-white px-4 py-2 rounded"
        >
          Join Classroom
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <form onSubmit={handleCreate} className="mt-4 p-4 border rounded">
          <h4 className="font-semibold mb-2">New Classroom</h4>
          <input
            type="text"
            placeholder="Classroom Name"
            value={newClass.name}
            onChange={(e) => setNewClass({ ...newClass, name: e.target.value })}
            className="border p-2 mr-2 mb-2"
            required
          />
          <input
            type="text"
            placeholder="Description"
            value={newClass.description}
            onChange={(e) =>
              setNewClass({ ...newClass, description: e.target.value })
            }
            className="border p-2 mr-2 mb-2"
          />
          <button className="bg-blue-600 text-white px-3 py-1 rounded">
            Create
          </button>
        </form>
      )}

      {/* Join form */}
      {showJoin && (
        <form onSubmit={handleJoin} className="mt-4 p-4 border rounded">
          <h4 className="font-semibold mb-2">Join Classroom</h4>
          <input
            type="text"
            placeholder="Enter Code"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
            className="border p-2 mr-2 mb-2"
            required
          />
          <button className="bg-green-600 text-white px-3 py-1 rounded">
            Join
          </button>
        </form>
      )}
    </div>
  );
}
