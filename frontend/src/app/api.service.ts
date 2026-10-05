import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Summary { total: number; restaurants: number; clubs: number; bars: number; cafes: number; }
export interface Club { id: number; name: string; address: string | null; latitude: number; longitude: number; opening_hours: string | null; }
export interface Recommendation { club_id: number | null; club_name: string; restaurant_id: number; restaurant_name: string; restaurant_address: string | null; opening_hours: string | null; data_quality_score: number; latitude: number; longitude: number; distance_meters: number; walking_minutes: number; google_open_now: boolean | null; google_maps_uri: string | null; open_status: 'open_confirmed' | 'open_by_schedule' | 'closed_confirmed' | 'closed_by_schedule' | 'hours_available' | 'unknown'; }
export interface RecommendationPage { items: Recommendation[]; total: number; page: number; page_size: number; pages: number; }

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  summary(): Observable<Summary> { return this.http.get<Summary>('/api/summary'); }
  clubs(): Observable<Club[]> { return this.http.get<Club[]>('/api/clubs'); }
  recommendations(clubId: number | null, maxDistance: number, page: number, pageSize = 10, origin: {lat: number; lon: number} | null = null, visitTime: string | null = null, openOnly = false): Observable<RecommendationPage> {
    let params = new HttpParams().set('max_distance_meters', maxDistance).set('page', page).set('page_size', pageSize);
    if (clubId !== null) params = params.set('club_id', clubId);
    if (origin) params = params.set('origin_lat', origin.lat).set('origin_lon', origin.lon);
    if (visitTime) params = params.set('visit_time', visitTime);
    if (openOnly) params = params.set('open_only', true);
    return this.http.get<RecommendationPage>('/api/recommendations', { params });
  }
}
