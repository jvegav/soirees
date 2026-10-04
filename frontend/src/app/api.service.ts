import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Summary { total: number; restaurants: number; clubs: number; bars: number; cafes: number; }
export interface Club { id: number; name: string; address: string | null; latitude: number; longitude: number; opening_hours: string | null; }
export interface Recommendation { club_id: number; club_name: string; restaurant_id: number; restaurant_name: string; restaurant_address: string | null; opening_hours: string | null; data_quality_score: number; latitude: number; longitude: number; distance_meters: number; walking_minutes: number; }

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  summary(): Observable<Summary> { return this.http.get<Summary>('/api/summary'); }
  clubs(): Observable<Club[]> { return this.http.get<Club[]>('/api/clubs'); }
  recommendations(clubId: number | null, maxDistance: number): Observable<Recommendation[]> {
    let params = new HttpParams().set('max_distance_meters', maxDistance);
    if (clubId !== null) params = params.set('club_id', clubId);
    return this.http.get<Recommendation[]>('/api/recommendations', { params });
  }
}
