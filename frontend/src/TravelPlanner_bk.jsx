import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://travelagent-v2.onrender.com';

export default function TravelPlanner() {
  // Store user inputs without overriding them
  const [formData, setFormData] = useState({
    user_id: 'usr_dev_01',
    prompt: '',
    origin: '',
    destination: '',
    from_date: '',
    to_date: '',
    budget_inr: '',
    duration_days: '',
    trip_type: 'round_trip',
    include_local_cab: true,
    passport_verified: false,
    passport_data: {}
  });

  const [activeTab, setActiveTab] = useState('flights');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [error, setError] = useState(null);
  const [ocrData, setOcrData] = useState(null);
  const [ocrError, setOcrError] = useState(null);

  // History State
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);

  // Fetch search history for the active user_id
  const fetchHistory = async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      // const res = await fetch(`http://127.0.0.1:8000/api/v1/history/${formData.user_id}`);
      const res = await fetch(`${API_BASE}/api/v1/history/${formData.user_id}`);
      if (!res.ok) throw new Error(`Server returned status: ${res.status}`);
      const result = await res.json();
      if (result.status === 'Success') {
        setHistory(result.history || []);
      }
    } catch (err) {
      setHistoryError(err.message || 'Failed to fetch history.');
    } finally {
      setHistoryLoading(false);
    }
  };

  // Preserve user inputs directly as typed
  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  // Main API hit ONLY when clicking the Generate button
  const handleSearch = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // const res = await fetch('http://127.0.0.1:8000/api/v1/plan', {
      const res = await fetch(`${API_BASE}/api/v1/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          budget_inr: parseFloat(formData.budget_inr) || 0,
          duration_days: parseInt(formData.duration_days) || 1
        })
      });

      if (!res.ok) throw new Error(`Server returned status code: ${res.status}`);
      const result = await res.json();
      setData(result);
      
      if (result.budget_sufficient === false) {
        setActiveTab('itinerary');
      }
    } catch (err) {
      setError(err.message || 'Error communicating with AI service.');
    } finally {
      setLoading(false);
    }
  };

  // Passport upload ONLY verifies OCR and updates internal state (DOES NOT hit /plan)
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setOcrLoading(true);
    setOcrError(null);

    const body = new FormData();
    body.append('file', file);

    try {
      // const res = await fetch('http://127.0.0.1:8000/api/v1/ocr/passport', {
      const res = await fetch(`${API_BASE}/api/v1/ocr/passport`, {
        method: 'POST',
        body: body
      });
      const resData = await res.json();
      
      if (resData.status === 'success' || resData.passport_verified) {
        setOcrData(resData.passport_details);
        setFormData(prev => ({
          ...prev,
          passport_verified: true,
          passport_data: resData.passport_details
        }));
      } else {
        setOcrError('Could not verify passport. Please upload a clear document image or PDF.');
      }
    } catch (err) {
      setOcrError('Passport verification failed. Check server connection.');
    } finally {
      setOcrLoading(false);
    }
  };

  const flights = data?.breakdown?.flights || data?.flight_options || [];
  const hotels = data?.breakdown?.hotels || data?.hotels_options || [];
  const trains = data?.breakdown?.trains || data?.train_options || [];
  const buses = data?.breakdown?.buses || data?.bus_options || [];
  const cab = data?.breakdown?.local_cabs || data?.local_cab;
  const isBudgetSufficient = data?.budget_sufficient !== false;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '24px', fontFamily: 'Inter, system-ui, sans-serif', color: '#0f172a' }}>
      
      <header style={{ textAlign: 'center', marginBottom: '32px' }}>
        <div style={{ display:'flex', alignItems:'center',justifyContent:'center',gap:'14px', marginBottom:'8px'}}>
          <h1 style={{ 
            fontSize: '2.5rem', 
            fontWeight: '800',
            lineHeight: '1.3',
            paddingBottom: '8px', 
            background: 'linear-gradient(to right, #2563eb, #0d9488)', 
            WebkitBackgroundClip: 'text', 
            backgroundClip: 'text',
            WebkitTextFillColor: 'transparent', 
            margin: '0 0 8px 0',
            display: 'inline-block'
          }}>
            TravelAgent AI Engine
          </h1>
        </div>
        <p style={{ color: '#64748b', margin: '0px' }}>Autonomous Multi-Modal Travel Itinerary & Budget Generator</p>
      </header>

      {/* FORM: Keeps user input intact */}
      <form onSubmit={handleSearch} style={{ background: '#ffffff', padding: '24px', borderRadius: '16px', border: '1px solid #e2e8f0', boxShadow: '0 4px 10px rgba(0,0,0,0.03)', marginBottom: '32px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '16px' }}>
          
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>User ID</label>
            <input 
              name="user_id" 
              placeholder="e.g. usr_dev_01"
              value={formData.user_id} 
              onChange={handleInputChange} 
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }}  
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Origin Code</label>
            <input 
              name="origin" 
              placeholder="e.g. NAG"
              value={formData.origin} 
              onChange={handleInputChange} 
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} 
              required 
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Destination</label>
            <input 
              name="destination" 
              placeholder="e.g. BOM, DXB, London"
              value={formData.destination} 
              onChange={handleInputChange} 
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} 
              required 
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>From Date</label>
            <input 
              type="date" 
              name="from_date" 
              value={formData.from_date} 
              onChange={handleInputChange} 
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} 
              required 
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>To Date</label>
            <input 
              type="date" 
              name="to_date" 
              value={formData.to_date} 
              onChange={handleInputChange} 
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} 
              required 
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Budget (INR ₹)</label>
            <input 
              type="number" 
              name="budget_inr" 
              placeholder="e.g. 45000"
              value={formData.budget_inr} 
              onChange={handleInputChange} 
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} 
              required 
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Duration (Days)</label>
            <input 
              type="number" 
              name="duration_days" 
              placeholder="e.g. 3"
              value={formData.duration_days} 
              onChange={handleInputChange} 
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} 
              required 
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Trip Type</label>
            <select 
              name="trip_type" 
              value={formData.trip_type} 
              onChange={handleInputChange} 
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }}
            >
              <option value="round_trip">Round Trip</option>
              <option value="one_way">One Way</option>
            </select>
          </div>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>AI Prompt / Specific Preferences</label>
          <input 
            name="prompt" 
            placeholder="e.g. Plan a scenic trip with popular sights and authentic local food."
            value={formData.prompt} 
            onChange={handleInputChange} 
            style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} 
          />
        </div>

        <button 
          type="submit" 
          disabled={loading} 
          style={{ width: '100%', padding: '14px', background: loading ? '#94a3b8' : 'linear-gradient(to right, #2563eb, #1d4ed8)', color: '#ffffff', fontWeight: '600', border: 'none', borderRadius: '8px', cursor: loading ? 'not-allowed' : 'pointer' }}
        >
          {loading ? 'Synthesizing Live Data & Generating Itinerary...' : 'Generate Real-Time Travel Package'}
        </button>
      </form>

      {error && <div style={{ padding: '16px', background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', borderRadius: '8px', marginBottom: '24px' }}>{error}</div>}

      {/* OCR GATE BANNER */}
      {data && data.is_international && !formData.passport_verified && (
        <div style={{ background: '#fff7ed', border: '1px solid #ffedd5', padding: '24px', borderRadius: '16px', textAlign: 'center', marginBottom: '24px' }}>
          <h3 style={{ margin: '0 0 8px 0', color: '#c2410c' }}>🛂 International Trip: Passport Verification Required</h3>
          <p style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#9a3412' }}>
            This trip crosses international borders. Please upload your passport document. Once verified, click <strong>Generate Real-Time Travel Package</strong> above to fetch live flights, hotels, and itinerary.
          </p>
          
          <input type="file" onChange={handleFileUpload} disabled={ocrLoading} style={{ fontSize: '14px' }} />
          
          {ocrLoading && <p style={{ color: '#ea580c', fontSize: '13px', marginTop: '10px' }}>Verifying document with OCR...</p>}
          {ocrError && <p style={{ color: '#dc2626', fontSize: '13px', marginTop: '10px' }}>{ocrError}</p>}
        </div>
      )}

      {/* PASSPORT VERIFIED SUCCESS BADGE */}
      {formData.passport_verified && ocrData && (
        <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', padding: '14px 18px', borderRadius: '12px', marginBottom: '24px', fontSize: '13px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ color: '#15803d', fontWeight: '700' }}>Passport Verified ✅</span> — Holder: <strong>{ocrData.full_name || 'Verified'}</strong> ({ocrData.passport_number || 'Valid'})
          </div>
          <span style={{ color: '#166534', fontSize: '12px' }}>Ready to generate international packages</span>
        </div>
      )}

      {/* TRIP DETAILS & TABS */}
      {data && (!data.is_international || formData.passport_verified) && (
        <div>
          {/* TOTAL COST CARD */}
          <div style={{ background: '#0f172a', color: '#ffffff', padding: '20px', borderRadius: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
            <div>
              <span style={{ fontSize: '14px', color: '#94a3b8' }}>Estimated Total Package Cost</span>
              <h2 style={{ margin: 0, fontSize: '2rem', color: isBudgetSufficient ? '#38bdf8' : '#f87171' }}>
                ₹{(data.calculated_cost_inr || data.estimated_cost_inr || 0).toLocaleString()}
              </h2>
            </div>
            <div style={{ textAlign: 'right' }}>
              <span style={{ background: '#1e293b', padding: '8px 16px', borderRadius: '20px', fontSize: '13px', color: '#cbd5e1', border: '1px solid #334155' }}>
                {formData.duration_days} Days / {formData.destination}
              </span>
              <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '6px' }}>
                Your Budget: ₹{parseFloat(formData.budget_inr || 0).toLocaleString()}
              </div>
            </div>
          </div>

          {/* INSUFFICIENT BUDGET WARNING BANNER */}
          {!isBudgetSufficient && (
            <div style={{ background: '#fef2f2', border: '1px solid #fecaca', padding: '16px', borderRadius: '12px', marginBottom: '20px', color: '#991b1b' }}>
              <strong>⚠️ Budget Too Low:</strong> Estimated requirement is ₹{data.calculated_cost_inr.toLocaleString()}, but your budget is ₹{parseFloat(formData.budget_inr || 0).toLocaleString()}. Increase your budget to unlock detailed hotel and transit bookings.
            </div>
          )}

          {/* TAB BAR */}
          <div style={{ display: 'flex', gap: '8px', borderBottom: '2px solid #e2e8f0', marginBottom: '20px', overflowX: 'auto' }}>
            {['flights', 'hotels', 'trains', 'buses', 'cabs', 'itinerary'].map((tab) => (
              <button
                key={tab}
                onClick={() => {
                  setActiveTab(tab);
                  if (tab === 'history') fetchHistory();
                }}
                disabled={!isBudgetSufficient && tab !== 'itinerary' && tab !== 'history'}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  background: 'none',
                  borderBottom: activeTab === tab ? '3px solid #2563eb' : '3px solid transparent',
                  fontWeight: activeTab === tab ? '700' : '500',
                  color: !isBudgetSufficient && tab !== 'itinerary' && tab !== 'history' ? '#cbd5e1' : activeTab === tab ? '#2563eb' : '#64748b',
                  cursor: !isBudgetSufficient && tab !== 'itinerary' && tab !== 'history' ? 'not-allowed' : 'pointer',
                  textTransform: 'capitalize',
                  whiteSpace: 'nowrap'
                }}
              >
                {tab} {!isBudgetSufficient && tab !== 'itinerary' && tab !== 'history' ? '🔒' : ''}
              </button>
            ))}
          </div>

          {/* FLIGHTS */}
          {activeTab === 'flights' && isBudgetSufficient && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
              {flights.length === 0 ? <p style={{ color: '#64748b' }}>No flight options retrieved.</p> : flights.map((f, i) => (
                <div key={i} style={{ border: '1px solid #e2e8f0', padding: '16px', borderRadius: '12px', background: '#fff', display: 'flex', alignItems: 'center', gap: '14px', boxShadow: '0 2px 4px rgba(0,0,0,0.03)' }}>
                  <img src={f.airline_logo} alt={f.airline} style={{ width: '42px', height: '42px', objectFit: 'contain', borderRadius: '6px' }} onError={(e) => { e.target.src = 'https://placehold.co/48x48?text=Flight'; }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: '700' }}>
                      <span>{f.airline}</span>
                      <span style={{ color: '#059669' }}>₹{f.price_inr?.toLocaleString()}</span>
                    </div>
                    <div style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
                      {f.departure_time} ➔ {f.arrival_time}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* HOTELS */}
          {activeTab === 'hotels' && isBudgetSufficient && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '20px' }}>
              {hotels.length === 0 ? <p style={{ color: '#64748b' }}>No hotel options retrieved.</p> : hotels.map((h, i) => (
                <div key={i} style={{ border: '1px solid #e2e8f0', borderRadius: '12px', overflow: 'hidden', background: '#fff', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' }}>
                  <img src={h.image_url} alt={h.name} style={{ width: '100%', height: '170px', objectFit: 'cover' }} onError={(e) => { e.target.src = 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=500&auto=format&fit=crop&q=60'; }} />
                  <div style={{ padding: '16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <h4 style={{ margin: 0, fontSize: '15px', fontWeight: '700' }}>{h.name}</h4>
                      <span style={{ color: '#059669', fontWeight: '700' }}>₹{h.price_per_night?.toLocaleString()}/night</span>
                    </div>
                    <div style={{ fontSize: '13px', color: '#64748b' }}>⭐ {h.rating || '4.2'} Rating</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* TRAINS */}
          {activeTab === 'trains' && isBudgetSufficient && (
            <div>
              {trains.length === 0 ? (
                <p style={{ color: '#64748b' }}>No direct train options found for this route (Ground transit disabled for international trips).</p>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
                  {trains.map((t, i) => (
                    <div key={i} style={{ border: '1px solid #e2e8f0', padding: '18px', borderRadius: '12px', background: '#fff', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                        <div>
                          <span style={{ fontSize: '11px', fontWeight: '700', padding: '2px 8px', borderRadius: '6px', background: '#e0e7ff', color: '#3730a3', textTransform: 'uppercase' }}>
                            {t.class_tier || 'IRCTC'}
                          </span>
                          <h4 style={{ margin: '6px 0 0 0', fontSize: '15px', color: '#0f172a' }}>{t.train_name}</h4>
                        </div>
                        <span style={{ color: '#059669', fontWeight: '800', fontSize: '16px' }}>
                          ₹{t.total_price_inr?.toLocaleString()}
                        </span>
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b', marginTop: '10px', display: 'flex', justifyContent: 'space-between' }}>
                        <span>🕒 {t.departure_time || 'Dep'} ➔ {t.arrival_time || 'Arr'}</span>
                        <span>⏱️ {t.duration}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* BUSES */}
          {activeTab === 'buses' && isBudgetSufficient && (
            <div>
              {buses.length === 0 ? (
                <p style={{ color: '#64748b' }}>No bus services available on this route.</p>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
                  {buses.map((b, i) => (
                    <div key={i} style={{ border: '1px solid #e2e8f0', padding: '18px', borderRadius: '12px', background: '#fff', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                        <div>
                          <span style={{ fontSize: '11px', fontWeight: '700', padding: '2px 8px', borderRadius: '6px', background: '#fef3c7', color: '#92400e' }}>
                            {b.bus_type || 'AC Sleeper'}
                          </span>
                          <h4 style={{ margin: '6px 0 0 0', fontSize: '15px', color: '#0f172a' }}>{b.bus_operator}</h4>
                        </div>
                        <span style={{ color: '#059669', fontWeight: '800', fontSize: '16px' }}>
                          ₹{b.total_price_inr?.toLocaleString()}
                        </span>
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b', marginTop: '10px', display: 'flex', justifyContent: 'space-between' }}>
                        <span>🕒 {b.departure_time || 'Dep'} ➔ {b.arrival_time || 'Arr'}</span>
                        <span>⏱️ {b.duration}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* CABS */}
          {activeTab === 'cabs' && isBudgetSufficient && (
            <div>
              {cab?.cab_service ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
                  <div style={{ border: '2px solid #2563eb', padding: '20px', borderRadius: '14px', background: '#ffffff', boxShadow: '0 4px 10px rgba(37,99,235,0.08)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ fontSize: '11px', fontWeight: '700', textTransform: 'uppercase', padding: '3px 8px', borderRadius: '6px', background: '#dbeafe', color: '#1d4ed8' }}>
                        Recommended Cab
                      </span>
                      <span style={{ color: '#059669', fontWeight: '800', fontSize: '16px' }}>
                        ₹{cab.total_cab_cost_inr?.toLocaleString()} Total
                      </span>
                    </div>

                    <h3 style={{ margin: '8px 0 4px 0', fontSize: '18px', color: '#0f172a' }}>{cab.cab_service}</h3>
                    <p style={{ margin: '0 0 10px 0', fontSize: '13px', color: '#64748b' }}>Vehicle: <strong>{cab.vehicle_type || 'Sedan'}</strong></p>

                    <div style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: '8px', fontSize: '13px', color: '#334155', marginBottom: '12px', border: '1px solid #e2e8f0' }}>
                      📍 <strong>Includes:</strong> {cab.inclusions || 'Airport transfers & daily sightseeing'}
                    </div>

                    <div style={{ fontSize: '14px', color: '#475569', fontWeight: '600' }}>
                      Daily Rate: ₹{cab.daily_rate_inr?.toLocaleString()} / day
                    </div>
                  </div>

                  {cab.alternatives?.map((alt, idx) => (
                    <div key={idx} style={{ border: '1px solid #e2e8f0', padding: '20px', borderRadius: '14px', background: '#ffffff', boxShadow: '0 2px 4px rgba(0,0,0,0.03)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <span style={{ fontSize: '11px', fontWeight: '700', textTransform: 'uppercase', padding: '3px 8px', borderRadius: '6px', background: '#f1f5f9', color: '#475569' }}>
                          Option {idx + 2}
                        </span>
                        <span style={{ color: '#059669', fontWeight: '700', fontSize: '15px' }}>
                          ₹{alt.total_cab_cost_inr?.toLocaleString()} Total
                        </span>
                      </div>

                      <h3 style={{ margin: '8px 0 4px 0', fontSize: '17px', color: '#0f172a' }}>{alt.service_name}</h3>
                      <p style={{ margin: '0 0 10px 0', fontSize: '13px', color: '#64748b' }}>Vehicle: <strong>{alt.vehicle_type}</strong></p>

                      <div style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: '8px', fontSize: '13px', color: '#334155', marginBottom: '12px', border: '1px solid #e2e8f0' }}>
                        📍 <strong>Includes:</strong> {alt.inclusions}
                      </div>

                      <div style={{ fontSize: '13px', color: '#64748b' }}>
                        Daily Rate: ₹{alt.daily_rate_inr?.toLocaleString()} / day
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#64748b' }}>No local cab options selected.</p>
              )}
            </div>
          )}

          {/* ITINERARY */}
          {activeTab === 'itinerary' && (
            <div style={{ background: '#f8fafc', padding: '24px', borderRadius: '12px', border: '1px solid #e2e8f0', lineHeight: '1.6' }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {data.itinerary || data.draft_itinerary}
              </ReactMarkdown>
            </div>
          )}

          {/* HISTORY TAB */}
          {activeTab === 'history' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ margin: 0, fontSize: '18px', color: '#0f172a' }}>Saved Search History for {formData.user_id}</h3>
                <button 
                  onClick={fetchHistory} 
                  disabled={historyLoading}
                  style={{ padding: '6px 14px', background: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '6px', cursor: 'pointer', fontSize: '12px', fontWeight: '600' }}
                >
                  {historyLoading ? 'Refreshing...' : '🔄 Refresh'}
                </button>
              </div>

              {historyError && (
                <div style={{ padding: '12px', background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', borderRadius: '8px', marginBottom: '16px', fontSize: '13px' }}>
                  {historyError}
                </div>
              )}

              {historyLoading ? (
                <p style={{ color: '#64748b' }}>Loading past itineraries...</p>
              ) : history.length === 0 ? (
                <div style={{ padding: '32px', textAlign: 'center', background: '#f8fafc', borderRadius: '12px', border: '1px dashed #cbd5e1', color: '#64748b' }}>
                  No past trip records found for <strong>{formData.user_id}</strong>. Generate a plan first!
                </div>
              ) : (
                <div style={{ display: 'grid', gap: '16px' }}>
                  {history.map((item, idx) => (
                    <div key={idx} style={{ border: '1px solid #e2e8f0', padding: '20px', borderRadius: '12px', background: '#ffffff', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                        <div>
                          <span style={{ fontSize: '11px', fontWeight: '700', padding: '3px 8px', borderRadius: '6px', background: '#dbeafe', color: '#1d4ed8' }}>
                            Trip #{idx + 1}
                          </span>
                          <p style={{ margin: '8px 0 0 0', fontWeight: '600', color: '#0f172a', fontSize: '14px' }}>
                            Prompt: "{item.prompt || item.user_input}"
                          </p>
                        </div>
                        <span style={{ color: '#059669', fontWeight: '800', fontSize: '16px' }}>
                          ₹{Number(item.estimated_cost || item.calculated_cost_inr || 0).toLocaleString()}
                        </span>
                      </div>

                      <div style={{ maxHeight: '180px', overflowY: 'auto', background: '#f8fafc', padding: '14px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '13px', lineHeight: '1.5' }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {item.itinerary || item.draft_itinerary || 'No itinerary content recorded.'}
                        </ReactMarkdown>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}