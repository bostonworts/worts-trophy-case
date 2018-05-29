class Place < Struct.new(:value)
  VALUES = 1..4

  def self.all
    VALUES.map do |value|
      Place.new(value)
    end
  end

  def description
    if value == 4
      "HM"
    else
      value.ordinalize
    end
  end
end
