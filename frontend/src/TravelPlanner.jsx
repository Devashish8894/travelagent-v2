import React, { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const extractTime = (timeStr) => {
  if (!timeStr || typeof timeStr !== 'string') return '12:00';
  if (timeStr.includes('T')) {
    const p = timeStr.split('T')[1];
    return p ? p.slice(0, 5) : '12:00';
  }
  if (timeStr.includes(' ')) {
    const parts = timeStr.trim().split(/\s+/);
    return parts[1] ? parts[1].slice(0, 5) : parts[0].slice(0, 5);
  }
  return timeStr.slice(0, 5);
};

export default function TravelPlanner() {
  const [formData, setFormData] = useState({
    user_id: '',
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

  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);

  const fetchHistory = async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/history/${formData.user_id}`);
      if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
      const result = await res.json();
      if (result.status === 'Success') setHistory(result.history || []);
    } catch (err) {
      setHistoryError(err.message || 'Failed to fetch search history.');
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    const val = type === 'checkbox' ? checked : value;

    setFormData((prev) => {
      const updated = { ...prev, [name]: val };
      if (name === 'from_date' || name === 'to_date') {
        const from = name === 'from_date' ? value : prev.from_date;
        const to = name === 'to_date' ? value : prev.to_date;
        if (from && to) {
          const diffDays = Math.ceil((new Date(to) - new Date(from)) / (1000 * 60 * 60 * 24)) + 1;
          if (diffDays > 0) updated.duration_days = diffDays.toString();
        }
      }
      if (name === 'duration_days' && prev.from_date && Number(value) > 0) {
        const d = new Date(prev.from_date);
        d.setDate(d.getDate() + (parseInt(value, 10) - 1));
        updated.to_date = d.toISOString().split('T')[0];
      }
      return updated;
    });
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          budget_inr: parseFloat(formData.budget_inr) || 0,
          duration_days: parseInt(formData.duration_days, 10) || 1
        })
      });
      if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
      const result = await res.json();
      setData(result);
      if (result.budget_sufficient === false) setActiveTab('itinerary');
    } catch (err) {
      setError(err.message || 'Error communicating with AI service.');
    } finally {
      setLoading(false);
    }
  };
  
  const handleUpdateBudgetAndSearch = async () => {
    const requiredBudget = data?.estimated_cost_inr || calculatedPackageCost || formData.budget_inr;
    setFormData((prev) => ({ ...prev, budget_inr: requiredBudget.toString() }));
    
    setLoading(true);
    setError(null);
    try {
      const payload = {
        ...formData,
        budget_inr: parseFloat(requiredBudget),
        duration_days: parseInt(formData.duration_days, 10) || 1
      };
      const res = await fetch(`${API_BASE}/api/v1/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
      const result = await res.json();
      setData(result);
      if (result.budget_sufficient === false) setActiveTab('itinerary');
      else setActiveTab('flights');
    } catch (err) {
      setError(err.message || 'Error communicating with AI service.');
    } finally {
      setLoading(false);
    }
  };
  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setOcrLoading(true);
    setOcrError(null);
    const body = new FormData();
    body.append('file', file);
    try {
      const res = await fetch(`${API_BASE}/api/v1/ocr/passport`, { method: 'POST', body });
      const resData = await res.json();
      if (resData.status === 'success' || resData.passport_verified) {
        setOcrData(resData.passport_details);
        setFormData((prev) => ({ ...prev, passport_verified: true, passport_data: resData.passport_details }));
      } else {
        setOcrError('Could not verify passport document.');
      }
    } catch (err) {
      setOcrError('Passport verification failed.');
    } finally {
      setOcrLoading(false);
    }
  };

  // Robust field reading across all API response signatures
  const rawFlights = data?.flight_options || data?.breakdown?.flights || [];
  const hotels = data?.hotels_options || data?.breakdown?.hotels || [];
  const trains = data?.train_options || data?.breakdown?.trains || [];
  const buses = data?.bus_options || data?.breakdown?.buses || [];
  const cabs = data?.cabs_options || (Array.isArray(data?.breakdown?.cabs) ? data.breakdown.cabs : []);
  let cab = data?.local_cab || data?.breakdown?.local_cabs || data?.breakdown?.cabs || {};
  if (Array.isArray(cab)) {
    cab = cab.length > 0 ? cab[0] : {};
  }

  const tripDays = parseInt(formData.duration_days, 10) || 1;
  const tripNights = Math.max(1, tripDays - 1);

  const { outboundFlights, returnFlights } = useMemo(() => {
    if (!Array.isArray(rawFlights) || rawFlights.length === 0) return { outboundFlights: [], returnFlights: [] };
    if (formData.trip_type === 'one_way') return { outboundFlights: rawFlights, returnFlights: [] };

    const out = rawFlights.filter((f) => f && (f.direction === 'outbound' || f.trip_direction === 'outbound'));
    const ret = rawFlights.filter((f) => f && (f.direction === 'return' || f.direction === 'inbound' || f.trip_direction === 'return'));

    if (out.length > 0 || ret.length > 0) return { outboundFlights: out, returnFlights: ret };
    const half = Math.ceil(rawFlights.length / 2);
    return { outboundFlights: rawFlights.slice(0, half), returnFlights: rawFlights.slice(half) };
  }, [rawFlights, formData.trip_type]);

  const lowestOutboundFlight = useMemo(() => {
    if (!outboundFlights.length) return null;
    return [...outboundFlights].sort((a, b) => (Number(a?.price_inr) || 0) - (Number(b?.price_inr) || 0))[0];
  }, [outboundFlights]);

  const lowestReturnFlight = useMemo(() => {
    if (!returnFlights.length) return null;
    return [...returnFlights].sort((a, b) => (Number(a?.price_inr) || 0) - (Number(b?.price_inr) || 0))[0];
  }, [returnFlights]);

  const lowestHotel = useMemo(() => {
    if (!hotels.length) return null;
    return [...hotels].sort((a, b) => (Number(a?.price_per_night) || 0) - (Number(b?.price_per_night) || 0))[0];
  }, [hotels]);

  const lowestCab = useMemo(() => {
    if (cabs && cabs.length) {
      return [...cabs].sort((a, b) => (Number(a?.total_cab_cost_inr) || 0) - (Number(b?.total_cab_cost_inr) || 0))[0];
    }
    if (cab?.cab_service) {
      let lowest = { 
        service_name: cab.cab_service,
        vehicle_type: cab.vehicle_type,
        total_cab_cost_inr: cab.total_cab_cost_inr 
      };
      if (Array.isArray(cab.alternatives)) {
        cab.alternatives.forEach(alt => {
           if (alt.total_cab_cost_inr < lowest.total_cab_cost_inr) lowest = alt;
        });
      }
      return lowest;
    }
    return null;
  }, [cabs, cab]);

  const calculatedPackageCost = useMemo(() => {
    let cost = 0;
    if (lowestOutboundFlight?.price_inr) cost += Number(lowestOutboundFlight.price_inr);
    if (formData.trip_type === 'round_trip' && lowestReturnFlight?.price_inr) {
      cost += Number(lowestReturnFlight.price_inr);
    }
    if (lowestHotel?.price_per_night) cost += Number(lowestHotel.price_per_night) * tripNights;
    if (lowestCab?.total_cab_cost_inr) cost += Number(lowestCab.total_cab_cost_inr);

    return cost > 0 ? cost : Number(data?.calculated_cost_inr || data?.estimated_cost_inr || 0);
  }, [lowestOutboundFlight, lowestReturnFlight, lowestHotel, lowestCab, tripNights, formData.trip_type, data]);

  const currentBudget = parseFloat(formData.budget_inr) || 0;
  const isBudgetShort = calculatedPackageCost > 0 && currentBudget < calculatedPackageCost;
  const isBudgetSufficient = data ? !isBudgetShort && data.budget_sufficient !== false : true;

  const handleApplyCalculatedBudget = () => {
    setFormData((prev) => ({ ...prev, budget_inr: calculatedPackageCost.toString() }));
  };

  const renderFlightCard = (f, i, isOutbound, lowest) => {
    const isLowest = lowest?.flight_number === f?.flight_number;
    const segments = Array.isArray(f?.segments) && f.segments.length > 0 ? f.segments : [];
    const isDirect = f?.is_direct ?? (segments.length <= 1 && !segments[0]?.layover_after);

    return (
      <div
        key={i}
        style={{
          border: isLowest ? '2px solid #2563eb' : '1px solid #e2e8f0',
          padding: '16px',
          borderRadius: '12px',
          background: isLowest ? '#f8faff' : '#ffffff',
          boxShadow: '0 2px 4px rgba(0,0,0,0.02)'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <img
            src={f?.airline_logo || `https://placehold.co/40x40?text=${(f?.airline || 'FL').slice(0, 2)}`}
            alt={f?.airline || 'Airline'}
            style={{ width: '40px', height: '40px', objectFit: 'contain' }}
            onError={(e) => { e.target.src = 'https://placehold.co/40x40?text=FL'; }}
          />
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: '700' }}>
              <span>{f?.airline} <small style={{ color: '#64748b', fontWeight: '400' }}>({f?.flight_number})</small></span>
              <div style={{ textAlign: 'right' }}>
                <span style={{ color: '#059669', fontSize: '16px' }}>₹{Number(f?.price_inr || 0).toLocaleString()}</span>
                <div style={{ fontSize: '10px', color: '#64748b', fontWeight: '500' }}>
                  {isDirect ? 'Direct Non-Stop' : `${segments.length} Legs Connecting`}
                </div>
              </div>
            </div>
            <div style={{ fontSize: '12px', color: '#475569', marginTop: '4px', display: 'flex', justifyContent: 'space-between' }}>
              <span>🕒 {extractTime(f?.departure_time)} ➔ {extractTime(f?.arrival_time)} ({f?.total_duration})</span>
              <span style={{ color: '#2563eb', fontWeight: '600' }}>
                {isOutbound ? `${formData.origin} ➔ ${formData.destination}` : `${formData.destination} ➔ ${formData.origin}`}
              </span>
            </div>
          </div>
        </div>

        <div style={{ marginTop: '8px', fontSize: '11px', fontWeight: '700' }}>
          {isDirect ? (
            <span style={{ color: '#15803d', background: '#dcfce7', padding: '2px 8px', borderRadius: '4px' }}>
              🟢 Non-Stop Direct Flight
            </span>
          ) : (
            <span style={{ color: '#b45309', background: '#fef3c7', padding: '2px 8px', borderRadius: '4px' }}>
              🟠 1-Stop Connecting Flight
            </span>
          )}
        </div>

        {segments.length > 0 && (
          <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px dashed #e2e8f0', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {segments.map((seg, sIdx) => (
              <div key={sIdx} style={{ fontSize: '12px', background: '#f8fafc', padding: '6px 10px', borderRadius: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: '600', color: '#1e293b' }}>
                  <span>✈️ Leg {sIdx + 1}: {seg.airline} ({seg.flight_number})</span>
                  <span>{seg.from_code} ➔ {seg.to_code}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748b', fontSize: '11px', marginTop: '2px' }}>
                  <span>Dep: {extractTime(seg.departure_time)}</span>
                  <span>Arr: {extractTime(seg.arrival_time)} {seg.day_shift || ''}</span>
                </div>
                {seg.layover_after && (
                  <div style={{ marginTop: '3px', color: '#d97706', fontWeight: '600', fontSize: '11px' }}>
                    ⏳ Layover: {seg.layover_after}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {isLowest && (
          <div style={{ marginTop: '8px', fontSize: '11px', fontWeight: '700', color: '#2563eb', textTransform: 'uppercase' }}>
            ⭐ Lowest Fare Option
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '24px', fontFamily: 'Inter, system-ui, sans-serif', color: '#0f172a' }}>
      <header style={{ textAlign: 'center', marginBottom: '32px' }}>
        <h1 style={{
          fontSize: '2.5rem',
          fontWeight: '800',
          lineHeight: '1.3',
          background: 'linear-gradient(to right, #2563eb, #0d9488)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          margin: '0 0 8px 0',
          display: 'inline-block'
        }}>
          TravelAgent AI Engine
        </h1>
        <p style={{ color: '#64748b', margin: '0px' }}>Dynamic Multi-Modal Travel Itinerary & Lowest Cost Package Planner</p>
      </header>

      {/* SEARCH FORM */}
      <form onSubmit={handleSearch} style={{ background: '#ffffff', padding: '24px', borderRadius: '16px', border: '1px solid #e2e8f0', boxShadow: '0 4px 10px rgba(0,0,0,0.03)', marginBottom: '32px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '16px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>User ID</label>
            <input name="user_id" value={formData.user_id} onChange={handleInputChange} style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} />
          </div>
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Origin</label>
            <input name="origin" placeholder="e.g. BOM" value={formData.origin} onChange={handleInputChange} style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} required />
          </div>
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Destination</label>
            <input name="destination" placeholder="e.g. LAX or DEL" value={formData.destination} onChange={handleInputChange} style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} required />
          </div>
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Start Date</label>
            <input type="date" name="from_date" value={formData.from_date} onChange={handleInputChange} style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} required />
          </div>
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>End Date</label>
            <input type="date" name="to_date" min={formData.from_date} value={formData.to_date} onChange={handleInputChange} style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} required />
          </div>
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Duration (Days)</label>
            <input type="number" name="duration_days" value={formData.duration_days} onChange={handleInputChange} style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} required />
          </div>
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Budget (INR ₹)</label>
            <input type="number" name="budget_inr" value={formData.budget_inr} onChange={handleInputChange} style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} required />
          </div>
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Trip Type</label>
            <select name="trip_type" value={formData.trip_type} onChange={handleInputChange} style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }}>
              <option value="round_trip">Round Trip</option>
              <option value="one_way">One Way</option>
            </select>
          </div>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ fontSize: '13px', fontWeight: '600', color: '#475569' }}>Travel Preferences / Prompt</label>
          <input name="prompt" placeholder="e.g. Scenic views, morning departures, executive travel." value={formData.prompt} onChange={handleInputChange} style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', marginTop: '4px', boxSizing: 'border-box' }} />
        </div>

        <button type="submit" disabled={loading} style={{ width: '100%', padding: '14px', background: loading ? '#94a3b8' : 'linear-gradient(to right, #2563eb, #1d4ed8)', color: '#ffffff', fontWeight: '600', border: 'none', borderRadius: '8px', cursor: loading ? 'not-allowed' : 'pointer' }}>
          {loading ? 'Synthesizing Live Dynamic Options via Gemini 3.8 Flash...' : 'Generate Real-Time Travel Package'}
        </button>
      </form>

      {error && <div style={{ padding: '16px', background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', borderRadius: '8px', marginBottom: '24px' }}>{error}</div>}

      {/* OCR GATE BANNER */}
      {data && data.is_international && !formData.passport_verified && (
        <div style={{ background: '#fff7ed', border: '1px solid #ffedd5', padding: '24px', borderRadius: '16px', textAlign: 'center', marginBottom: '24px' }}>
          <h3 style={{ margin: '0 0 8px 0', color: '#c2410c' }}>🛂 International Trip: Passport Verification Required</h3>
          <p style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#9a3412' }}>This trip crosses international borders. Please upload your passport document.</p>
          <input type="file" onChange={handleFileUpload} disabled={ocrLoading} style={{ fontSize: '14px' }} />
          {ocrLoading && <p style={{ color: '#ea580c', fontSize: '13px', marginTop: '10px' }}>Verifying document with OCR...</p>}
          {ocrError && <p style={{ color: '#dc2626', fontSize: '13px', marginTop: '10px' }}>{ocrError}</p>}
        </div>
      )}

      {/* PASSPORT VERIFIED SUCCESS BADGE */}
      {formData.passport_verified && (
        <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', padding: '14px 18px', borderRadius: '12px', marginBottom: '24px', fontSize: '13px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: '#15803d', fontWeight: '700' }}>Passport Verified ✅ — Passenger: <strong>{ocrData?.full_name || 'Verified Passenger'}</strong></span>
          <span style={{ color: '#166534', fontSize: '12px' }}>Unlocked International Package</span>
        </div>
      )}

      {/* MAIN DATA VIEW */}
      {data && (!data.is_international || formData.passport_verified) && (
        <div>
          {/* PACKAGE VALUE OVERVIEW */}
          <div style={{ background: '#0f172a', color: '#ffffff', padding: '24px', borderRadius: '16px', display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
            <div>
              <span style={{ fontSize: '13px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Lowest Combined Package Cost
              </span>
              <h2 style={{ margin: '4px 0 0 0', fontSize: '2.2rem', color: isBudgetShort ? '#f87171' : '#38bdf8' }}>
                ₹{calculatedPackageCost.toLocaleString()}
              </h2>
              <div style={{ fontSize: '13px', color: '#94a3b8', marginTop: '6px' }}>
                Outbound: ₹{(lowestOutboundFlight?.price_inr || 0).toLocaleString()} | 
                Return: ₹{(formData.trip_type === 'round_trip' ? (lowestReturnFlight?.price_inr || 0) : 0).toLocaleString()} | 
                Hotel ({tripNights}N): ₹{((lowestHotel?.price_per_night || 0) * tripNights).toLocaleString()} | 
                Cab: ₹{(lowestCab?.total_cab_cost_inr || 0).toLocaleString()}
              </div>
            </div>

            <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
              <div style={{ background: '#1e293b', padding: '6px 14px', borderRadius: '20px', fontSize: '13px', color: '#cbd5e1', border: '1px solid #334155' }}>
                {tripDays} Days ({formData.from_date} ➔ {formData.to_date})
              </div>
              <div style={{ fontSize: '13px', color: '#cbd5e1' }}>
                Your Current Budget: <strong>₹{currentBudget.toLocaleString()}</strong>
              </div>

              {isBudgetShort && (
                <button
                  type="button"
                  onClick={handleApplyCalculatedBudget}
                  style={{
                    marginTop: '4px',
                    padding: '8px 16px',
                    background: '#f59e0b',
                    color: '#000000',
                    fontWeight: '700',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontSize: '13px'
                  }}
                >
                  ⚡ Match Budget to ₹{calculatedPackageCost.toLocaleString()}
                </button>
              )}
            </div>
          </div>

          {/* TABS HEADER */}
          <div style={{ display: 'flex', gap: '8px', borderBottom: '2px solid #e2e8f0', marginBottom: '20px', overflowX: 'auto' }}>
            {['flights', 'hotels', 'trains', 'buses', 'cabs', 'itinerary', 'history'].map((tab) => (
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

          {/* FLIGHTS TAB */}
          {activeTab === 'flights' && isBudgetSufficient && (
            <div>
              {formData.trip_type === 'round_trip' ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '24px' }}>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '14px' }}>
                      <h3 style={{ margin: 0, fontSize: '17px', color: '#1e40af' }}>🛫 Outbound Flights ({formData.from_date})</h3>
                      <span style={{ fontSize: '12px', fontWeight: '600', color: '#64748b' }}>Showing {outboundFlights.length} options</span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                      {outboundFlights.map((f, i) => renderFlightCard(f, i, true, lowestOutboundFlight))}
                    </div>
                  </div>

                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '14px' }}>
                      <h3 style={{ margin: 0, fontSize: '17px', color: '#0f766e' }}>🛬 Return Flights ({formData.to_date})</h3>
                      <span style={{ fontSize: '12px', fontWeight: '600', color: '#64748b' }}>Showing {returnFlights.length} options</span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                      {returnFlights.map((f, i) => renderFlightCard(f, i, false, lowestReturnFlight))}
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
                  {outboundFlights.map((f, i) => renderFlightCard(f, i, true, lowestOutboundFlight))}
                </div>
              )}
            </div>
          )}

          {/* HOTELS TAB (12 Options) */}
          {activeTab === 'hotels' && isBudgetSufficient && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ margin: 0, fontSize: '18px', color: '#0f172a' }}>🏨 Accommodations in {formData.destination}</h3>
                <span style={{ fontSize: '12px', fontWeight: '600', color: '#64748b', background: '#f1f5f9', padding: '4px 10px', borderRadius: '6px' }}>
                  Showing {hotels.length} verified options ({tripNights} Nights)
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '20px' }}>
                {hotels.map((h, i) => {
                  const isLowest = lowestHotel?.name === h?.name;
                  return (
                    <div
                      key={i}
                      style={{
                        border: isLowest ? '2px solid #2563eb' : '1px solid #e2e8f0',
                        borderRadius: '12px',
                        overflow: 'hidden',
                        background: '#fff',
                        boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between'
                      }}
                    >
                      <img
                        src={h?.image_url || 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=500&auto=format&fit=crop&q=60'}
                        alt={h?.name}
                        style={{ width: '100%', height: '160px', objectFit: 'cover' }}
                        onError={(e) => { e.target.src = 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=500&auto=format&fit=crop&q=60'; }}
                      />
                      <div style={{ padding: '16px', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                            <h4 style={{ margin: 0, fontSize: '15px', fontWeight: '700' }}>{h?.name}</h4>
                            <span style={{ color: '#059669', fontWeight: '700', fontSize: '15px' }}>₹{Number(h?.price_per_night || 0).toLocaleString()}</span>
                          </div>
                          <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '8px' }}>
                            ⭐ {h?.rating || '4.3'} Rating • <small>₹{(Number(h?.price_per_night || 0) * tripNights).toLocaleString()} total</small>
                          </div>
                          <div style={{ fontSize: '11px', color: '#475569', background: '#f8fafc', padding: '6px 8px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                            {h?.amenities || 'WiFi, Breakfast, Concierge'}
                          </div>
                        </div>
                        {isLowest && (
                          <div style={{ marginTop: '10px', fontSize: '11px', fontWeight: '700', color: '#2563eb', textTransform: 'uppercase' }}>
                            ⭐ Lowest Nightly Rate
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TRAINS TAB */}
          {activeTab === 'trains' && isBudgetSufficient && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ margin: 0, fontSize: '18px', color: '#0f172a' }}>🚆 Direct Train Routes ({formData.origin} ➔ {formData.destination})</h3>
                <span style={{ fontSize: '12px', fontWeight: '600', color: '#64748b' }}>Showing {trains.length} options</span>
              </div>
              {trains.length === 0 ? (
                <p style={{ color: '#64748b' }}>No direct train routes found for this itinerary (Flight travel route).</p>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
                  {trains.map((t, i) => (
                    <div key={i} style={{ border: '1px solid #e2e8f0', padding: '16px', borderRadius: '12px', background: '#fff' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <span style={{ fontSize: '11px', fontWeight: '700', padding: '2px 8px', borderRadius: '6px', background: '#e0e7ff', color: '#3730a3', textTransform: 'uppercase' }}>
                            {t?.class_tier}
                          </span>
                          <h4 style={{ margin: '6px 0 0 0', fontSize: '15px' }}>{t?.train_name} <small>({t?.train_number})</small></h4>
                        </div>
                        <span style={{ color: '#059669', fontWeight: '800', fontSize: '16px' }}>₹{Number(t?.total_price_inr || 0).toLocaleString()}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b', marginTop: '10px', display: 'flex', justifyContent: 'space-between' }}>
                        <span>🕒 {t?.departure_time} ➔ {t?.arrival_time}</span>
                        <span>⏱️ {t?.duration}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* BUSES TAB */}
          {activeTab === 'buses' && isBudgetSufficient && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ margin: 0, fontSize: '18px', color: '#0f172a' }}>🚌 Intercity Bus Services ({formData.origin} ➔ {formData.destination})</h3>
                <span style={{ fontSize: '12px', fontWeight: '600', color: '#64748b' }}>Showing {buses.length} options</span>
              </div>
              {buses.length === 0 ? (
                <p style={{ color: '#64748b' }}>No intercity bus routes available for this route (Flight travel route).</p>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
                  {buses.map((b, i) => (
                    <div key={i} style={{ border: '1px solid #e2e8f0', padding: '16px', borderRadius: '12px', background: '#fff' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <span style={{ fontSize: '11px', fontWeight: '700', padding: '2px 8px', borderRadius: '6px', background: '#fef3c7', color: '#92400e' }}>
                            {b?.bus_type}
                          </span>
                          <h4 style={{ margin: '6px 0 0 0', fontSize: '15px' }}>{b?.bus_operator}</h4>
                        </div>
                        <span style={{ color: '#059669', fontWeight: '800', fontSize: '16px' }}>₹{Number(b?.total_price_inr || 0).toLocaleString()}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b', marginTop: '10px', display: 'flex', justifyContent: 'space-between' }}>
                        <span>🕒 {b?.departure_time} ➔ {b?.arrival_time}</span>
                        <span>⏱️ {b?.duration}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* CABS TAB */}
          {activeTab === 'cabs' && isBudgetSufficient && (
            <div>
              {(() => {
                // Combine primary cab + alternatives into a clean list of 5 options
                const allCabOptions = [];
                if (cab?.cab_service) {
                  allCabOptions.push({
                    service_name: cab.cab_service,
                    vehicle_type: cab.vehicle_type || 'Standard Sedan',
                    daily_rate_inr: cab.daily_rate_inr || 2500,
                    total_cab_cost_inr: cab.total_cab_cost_inr || (cab.daily_rate_inr || 2500) * tripDays,
                    inclusions: cab.inclusions || 'Airport transfers & full-day sightseeing',
                    is_recommended: true
                  });
                }

                if (Array.isArray(cab?.alternatives)) {
                  cab.alternatives.forEach((alt) => {
                    allCabOptions.push({
                      service_name: alt.service_name,
                      vehicle_type: alt.vehicle_type || 'Economy / SUV',
                      daily_rate_inr: alt.daily_rate_inr,
                      total_cab_cost_inr: alt.total_cab_cost_inr || (alt.daily_rate_inr * tripDays),
                      inclusions: alt.inclusions || 'Sightseeing & city travel',
                      is_recommended: false
                    });
                  });
                }

                const displayCabs = allCabOptions.slice(0, 5);

                if (displayCabs.length === 0) {
                  return <p style={{ color: '#64748b' }}>No local cab options available for this destination.</p>;
                }

                return (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                      <h3 style={{ margin: 0, fontSize: '18px', color: '#0f172a' }}>
                        🚕 Available Cab & Chauffeur Services ({formData.destination})
                      </h3>
                      <span style={{ fontSize: '12px', fontWeight: '600', color: '#64748b', background: '#f1f5f9', padding: '4px 10px', borderRadius: '6px' }}>
                        Showing {displayCabs.length} options ({tripDays} Days)
                      </span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
                      {displayCabs.map((c, idx) => (
                        <div 
                          key={idx} 
                          style={{ 
                            border: c.is_recommended ? '2px solid #2563eb' : '1px solid #e2e8f0', 
                            padding: '20px', 
                            borderRadius: '14px', 
                            background: c.is_recommended ? '#f8faff' : '#ffffff',
                            boxShadow: '0 4px 6px rgba(0,0,0,0.03)',
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'space-between'
                          }}
                        >
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                              <span style={{ 
                                fontSize: '11px', 
                                fontWeight: '700', 
                                textTransform: 'uppercase', 
                                padding: '3px 8px', 
                                borderRadius: '6px', 
                                background: c.is_recommended ? '#dbeafe' : '#f1f5f9', 
                                color: c.is_recommended ? '#1d4ed8' : '#475569' 
                              }}>
                                {c.is_recommended ? '⭐ Recommended Option' : `Option #${idx + 1}`}
                              </span>
                              <span style={{ color: '#059669', fontWeight: '800', fontSize: '16px' }}>
                                ₹{Number(c.total_cab_cost_inr || 0).toLocaleString()} Total
                              </span>
                            </div>

                            <h3 style={{ margin: '8px 0 4px 0', fontSize: '17px', color: '#0f172a' }}>{c.service_name}</h3>
                            <p style={{ margin: '0 0 10px 0', fontSize: '13px', color: '#64748b' }}>
                              Vehicle: <strong>{c.vehicle_type}</strong>
                            </p>

                            <div style={{ background: '#f8fafc', padding: '10px 12px', borderRadius: '8px', fontSize: '12px', color: '#334155', marginBottom: '12px', border: '1px solid #e2e8f0' }}>
                              📍 <strong>Includes:</strong> {c.inclusions}
                            </div>
                          </div>

                          <div style={{ fontSize: '13px', color: '#475569', fontWeight: '600', borderTop: '1px dashed #e2e8f0', paddingTop: '10px' }}>
                            Daily Rate: ₹{Number(c.daily_rate_inr || 0).toLocaleString()} / day
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </div>
          )}
          
           

          {/* ITINERARY TAB */}
          {activeTab === 'itinerary' && (
            <div style={{ background: '#f8fafc', padding: '24px', borderRadius: '12px', border: '1px solid #e2e8f0', lineHeight: '1.6' }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {data.itinerary || data.draft_itinerary || 'No itinerary generated.'}
              </ReactMarkdown>
              {!isBudgetSufficient && (
                <div style={{ display: 'flex', justifyContent: 'center', marginTop: '30px' }}>
                  <button 
                    onClick={handleUpdateBudgetAndSearch}
                    disabled={loading}
                    style={{ 
                      padding: '14px 28px', 
                      background: '#2563eb', 
                      color: 'white', 
                      border: 'none', 
                      borderRadius: '8px', 
                      fontSize: '16px', 
                      fontWeight: 'bold', 
                      cursor: loading ? 'not-allowed' : 'pointer',
                      boxShadow: '0 4px 6px -1px rgba(37, 99, 235, 0.2)'
                    }}
                  >
                    {loading ? 'Recalculating...' : `Match Budget (₹${Number(data?.estimated_cost_inr || calculatedPackageCost).toLocaleString()}) & Continue`}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* HISTORY TAB */}
          {activeTab === 'history' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ margin: 0, fontSize: '18px' }}>Saved Search Records for {formData.user_id}</h3>
                <button onClick={fetchHistory} disabled={historyLoading} style={{ padding: '6px 14px', background: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '6px', cursor: 'pointer', fontSize: '12px', fontWeight: '600' }}>
                  {historyLoading ? 'Loading...' : '🔄 Refresh'}
                </button>
              </div>
              {history.length === 0 ? (
                <p style={{ color: '#64748b' }}>No saved search records found.</p>
              ) : (
                <div style={{ display: 'grid', gap: '14px' }}>
                  {history.map((h, i) => (
                    <div key={i} style={{ border: '1px solid #e2e8f0', padding: '16px', borderRadius: '10px', background: '#fff' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <strong>{h.origin} ➔ {h.destination}</strong>
                        <span style={{ color: '#059669', fontWeight: '700' }}>₹{Number(h.calculated_cost_inr || h.total_cost || 0).toLocaleString()}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                        {h.from_date} to {h.to_date} ({h.duration_days} Days)
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