class CompetitionType
  TYPES = %w(
    bjcp_sanctioned
    mcab_qualifier
    mcab_finals
    nhc_qualifier
    nhc_finals
    other
  ).freeze.map(&:freeze)

  def self.all
    TYPES.map do |key|
      new(key)
    end
  end

  def self.high_profile?(type)
    type.in? %w(
      mcab_qualifier
      mcab_finals
      nhc_qualifier
      nhc_finals
    )
  end

  attr_reader :key

  def initialize(key)
    @key = key
  end

  def description
    first, rest = key.titleize.split(" ")

    if rest.present?
      "#{first.upcase} #{rest}"
    else
      first
    end
  end
end
