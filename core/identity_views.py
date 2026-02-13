"""
Canonical user identity endpoint.

GET /api/me/ - Returns authenticated user's identity with role and context.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Alumno


class UserIdentityView(APIView):
    """
    GET /api/me/
    
    Returns canonical authenticated user identity.
    
    Response schema:
    {
        "id": int,
        "username": str,
        "email": str,
        "role": "athlete" | "coach" | "admin",
        "coach_id": int (optional, if role=athlete),
        "athlete_id": int (optional, if role=athlete)
    }
    
    Multi-tenant safe: Returns only current user's data.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Return canonical user identity"""
        user = request.user
        
        # Base identity (always present)
        identity = {
            "id": user.id,
            "username": user.username,
            "email": user.email or "",
        }
        
        # Check if user is an athlete (Alumno)
        try:
            alumno = Alumno.objects.select_related('entrenador').get(usuario=user)
            identity["role"] = "athlete"
            identity["athlete_id"] = alumno.id
            
            # Add coach_id if athlete has a coach
            if alumno.entrenador:
                identity["coach_id"] = alumno.entrenador.id
            
        except Alumno.DoesNotExist:
            # Not an athlete - could be coach, staff, or admin
            # For now, default to "coach" role
            # TODO: Add explicit Coach model check if needed
            identity["role"] = "coach"
        
        return Response(identity, status=status.HTTP_200_OK)
