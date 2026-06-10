unit tipos;

interface



const
   inf : Integer = 999999999;
   infReal : Real = 999999999999;
   infDouble : Double = 1e+15;

   cotaerror : Real = 0.000001;


type
   VectorEntero = Array of Integer;
   MatrizEntero = Array of Array of Integer;
   Matriz2Entero = Array of VectorEntero;
   Matriz3Entero = Array of Matriz2Entero;


   VectorBoolean = Array of Boolean;
   MatrizBoolean = Array of Array of Boolean;
   Matriz2Boolean = Array of VectorBoolean;

   Coordenadas = Record
      x, y : Real
      end;

   VectorCoordenadas = Array of Coordenadas;

   VectorReal = Array of Real;
   MatrizReal = Array of Array of Real;
   Matriz2Real = Array of VectorReal;
   Matriz3Real = Array of Array of VectorReal;


   VectorDouble = Array of Double;
   MatrizDouble = Array of Array of Double;
   Matriz2Double = Array of VectorDouble;
   Matriz3Double = Array of Matriz2Double;
   Matriz30Double = Array of MatrizDouble;
   Matriz40Double = Array of Matriz30Double;
   Matriz41Double = Array of Array of MatrizDouble;
   Matriz51Double = Array of Matriz41Double;

   VectorExtended = Array of Extended;



   VectorCadena = Array of String;



implementation

end.
