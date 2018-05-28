class CompetitionType
  TYPES = %w(
    bjcp_sanctioned
    mcab_qualifier
    mcab_finals
    nhc_qualifier
    nhc_finals
  ).freeze.map(&:freeze)

  def self.all
    TYPES.map do |key|
      new(key)
    end
  end

  attr_reader :key

  def initialize(key)
    @key = key
  end

  def description
    acronym, rest = key.titleize.split(" ")
    "#{acronym.upcase} #{rest}"
  end
end
