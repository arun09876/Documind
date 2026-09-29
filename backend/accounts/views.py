from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


def user_payload(user) -> dict:
    return {"id": user.id, "username": user.username, "email": user.email}


def tokens_for(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh), "user": user_payload(user)}


class RegisterSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[\w.]{3,30}$", error_messages={"invalid": "Use 3-30 letters, digits, _ or ."})
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is taken.")
        return value

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        validate_password(attrs["password"], User(username=attrs["username"], email=attrs["email"]))
        return attrs


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = User.objects.create_user(**s.validated_data)
        return Response(tokens_for(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """Accepts a username or an email address."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        identifier = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        if "@" in identifier:
            match = User.objects.filter(email__iexact=identifier).first()
            identifier = match.username if match else identifier
        user = authenticate(username=identifier, password=password)
        if user is None:
            return Response({"error": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(tokens_for(user))


class MeView(APIView):
    def get(self, request):
        return Response(user_payload(request.user))
