from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import httpx
from google.transit import gtfs_realtime_pb2
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FEEDS = {
    "34": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
    "nqrw": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    "alerts": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fall-alerts",
    "bus": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bus-company-14"
}

STATIONS = {
    "crown_heights": "640",
    "borough_hall": "R31",
    "atlantic": "R30",
    "59th": "R08",
    "union_sq": "R20"
}

TRAVEL_TIMES = {
    "crown_to_borough": 15,
    "crown_to_atlantic": 3,
    "atlantic_to_59th": 18,
    "crown_to_union": 20,
    "atlantic_transfer": 5
}

def parse_gtfs(data, route_id, stop_id, direction="N"):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    
    arrivals = []
    now = int(datetime.now().timestamp())
    
    for entity in feed.entity:
        if entity.HasField('trip_update'):
            trip = entity.trip_update
            if trip.trip.route_id == route_id:
                for stop in trip.stop_time_update:
                    if stop.stop_id.startswith(stop_id):
                        stop_direction = stop.stop_id[-1]
                        if stop_direction == direction:
                            eta = stop.arrival.time if stop.HasField('arrival') else stop.departure.time
                            minutes = max(0, (eta - now) // 60)
                            arrivals.append({
                                "route": route_id,
                                "minutes": int(minutes),
                                "time": datetime.fromtimestamp(eta).strftime("%I:%M %p"),
                                "eta_timestamp": eta
                            })
    
    return sorted(arrivals, key=lambda x: x['minutes'])[:8]

def parse_alerts(data):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    
    alerts = []
    relevant_routes = ['3', '4', 'N', 'R']
    
    for entity in feed.entity:
        if entity.HasField('alert'):
            alert = entity.alert
            routes = [ie.route_id for ie in alert.informed_entity if ie.HasField('route_id')]
            matching_routes = [r for r in routes if r in relevant_routes]
            
            if matching_routes:
                header = alert.header_text.translation[0].text if alert.header_text.translation else ""
                alerts.append({
                    "routes": matching_routes,
                    "text": header
                })
    
    return alerts

@app.get("/")
async def read_root():
    return FileResponse("index.html")

@app.get("/api/trains/{route}")
async def get_train(route: str, station: str = "crown_heights", direction: str = "N"):
    feed_key = "34" if route in ["3", "4"] else "nqrw"
    stop_id = STATIONS.get(station, STATIONS["crown_heights"])
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(FEEDS[feed_key])
        arrivals = parse_gtfs(response.content, route, stop_id, direction)
        return {"arrivals": arrivals}

@app.get("/api/bus/b45")
async def get_bus():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(FEEDS["bus"])
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            
            arrivals = []
            now = int(datetime.now().timestamp())
            
            for entity in feed.entity:
                if entity.HasField('trip_update'):
                    trip = entity.trip_update
                    if trip.trip.route_id == "B45":
                        for stop in trip.stop_time_update:
                            eta = stop.arrival.time if stop.HasField('arrival') else stop.departure.time
                            minutes = max(0, (eta - now) // 60)
                            arrivals.append({
                                "route": "B45",
                                "minutes": int(minutes),
                                "time": datetime.fromtimestamp(eta).strftime("%I:%M %p")
                            })
            
            return {"arrivals": sorted(arrivals, key=lambda x: x['minutes'])[:5]}
    except:
        return {"arrivals": []}

@app.get("/api/alerts")
async def get_alerts():
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(FEEDS["alerts"])
        alerts = parse_alerts(response.content)
        return {"alerts": alerts}

@app.get("/api/journey/{destination}")
async def get_journey(destination: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        if destination == "tandon":
            response_4 = await client.get(FEEDS["34"])
            trains_4 = parse_gtfs(response_4.content, "4", STATIONS["crown_heights"], "N")
            
            journeys = []
            for train in trains_4[:3]:
                arrival_at_borough = train["eta_timestamp"] + (TRAVEL_TIMES["crown_to_borough"] * 60)
                journeys.append({
                    "depart_crown": train["time"],
                    "depart_minutes": train["minutes"],
                    "arrive_borough": datetime.fromtimestamp(arrival_at_borough).strftime("%I:%M %p"),
                    "total_time": TRAVEL_TIMES["crown_to_borough"],
                    "line": "4"
                })
            
            return {"destination": "Borough Hall (NYU Tandon)", "journeys": journeys}
        
        elif destination == "union":
            response_4 = await client.get(FEEDS["34"])
            trains_4 = parse_gtfs(response_4.content, "4", STATIONS["crown_heights"], "N")
            
            journeys = []
            for train in trains_4[:3]:
                arrival_at_union = train["eta_timestamp"] + (TRAVEL_TIMES["crown_to_union"] * 60)
                journeys.append({
                    "depart_crown": train["time"],
                    "depart_minutes": train["minutes"],
                    "arrive_union": datetime.fromtimestamp(arrival_at_union).strftime("%I:%M %p"),
                    "total_time": TRAVEL_TIMES["crown_to_union"],
                    "line": "4"
                })
            
            return {"destination": "Union Square (NYU Washington Sq)", "journeys": journeys}
        
        elif destination == "59th":
            response_4 = await client.get(FEEDS["34"])
            response_nqrw = await client.get(FEEDS["nqrw"])
            
            trains_4 = parse_gtfs(response_4.content, "4", STATIONS["crown_heights"], "N")
            trains_n = parse_gtfs(response_nqrw.content, "N", STATIONS["atlantic"], "N")
            trains_r = parse_gtfs(response_nqrw.content, "R", STATIONS["atlantic"], "N")
            
            journeys = []
            for train_4 in trains_4[:2]:
                atlantic_arrival = train_4["eta_timestamp"] + (TRAVEL_TIMES["crown_to_atlantic"] * 60)
                
                for train_n in trains_n:
                    if train_n["eta_timestamp"] > atlantic_arrival + (TRAVEL_TIMES["atlantic_transfer"] * 60):
                        final_arrival = train_n["eta_timestamp"] + (TRAVEL_TIMES["atlantic_to_59th"] * 60)
                        total = (final_arrival - train_4["eta_timestamp"]) // 60
                        
                        journeys.append({
                            "depart_crown": train_4["time"],
                            "depart_minutes": train_4["minutes"],
                            "arrive_atlantic": datetime.fromtimestamp(atlantic_arrival).strftime("%I:%M %p"),
                            "depart_atlantic": train_n["time"],
                            "arrive_59th": datetime.fromtimestamp(final_arrival).strftime("%I:%M %p"),
                            "total_time": int(total),
                            "transfer_line": "N"
                        })
                        break
                
                for train_r in trains_r:
                    if train_r["eta_timestamp"] > atlantic_arrival + (TRAVEL_TIMES["atlantic_transfer"] * 60):
                        final_arrival = train_r["eta_timestamp"] + (TRAVEL_TIMES["atlantic_to_59th"] * 60)
                        total = (final_arrival - train_4["eta_timestamp"]) // 60
                        
                        journeys.append({
                            "depart_crown": train_4["time"],
                            "depart_minutes": train_4["minutes"],
                            "arrive_atlantic": datetime.fromtimestamp(atlantic_arrival).strftime("%I:%M %p"),
                            "depart_atlantic": train_r["time"],
                            "arrive_59th": datetime.fromtimestamp(final_arrival).strftime("%I:%M %p"),
                            "total_time": int(total),
                            "transfer_line": "R"
                        })
                        break
            
            return {"destination": "59th St-Columbus Circle", "journeys": journeys[:3]}
    
    return {"destination": destination, "journeys": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)